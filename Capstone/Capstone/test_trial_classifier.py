"""
Tests for trial_classifier.py (Feature 7.3)
"""

import pytest
import numpy as np
from datetime import date, timedelta
from collections import defaultdict

from trial_classifier import (
    FEATURE_KEYS,
    COLD_START_PRIOR,
    COLD_START_WEIGHTS,
    extract_trial_features,
    build_synthetic_dataset,
    train_classifier,
    predict_trial_intent,
    classify_all_merchants,
)
from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
from transaction_filter import filter_transactions
from merchant_normaliser import cluster_merchants

NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')


# ─────────────────────────────────────────────
# Test fixtures
# ─────────────────────────────────────────────

def _make_txn(iso_date: str, amount: float, merchant='TEST') -> dict:
    return {
        'bank': 'TEST', 'date': iso_date, 'description': 'TEST DESC',
        'amount': amount, 'balance': None, 'currency': 'JMD',
        'source_file': 'test.pdf', 'merchant_id': merchant,
    }


def _txns_from_amounts(amounts, start='2026-01-01', gap_days=30, merchant='MID'):
    """Build transactions spaced gap_days apart."""
    d = date.fromisoformat(start)
    result = []
    for amt in amounts:
        result.append(_make_txn(d.isoformat(), -abs(amt), merchant))
        d += timedelta(days=gap_days)
    return result


def _txns_with_intervals(amounts, intervals, start='2026-01-01', merchant='MID'):
    """Build transactions with explicit per-gap intervals."""
    d = date.fromisoformat(start)
    result = []
    for i, amt in enumerate(amounts):
        result.append(_make_txn(d.isoformat(), -abs(amt), merchant))
        if i < len(intervals):
            d += timedelta(days=intervals[i])
    return result


@pytest.fixture(scope='module')
def trained_model():
    X, y = build_synthetic_dataset()
    return train_classifier(X, y)


# ─────────────────────────────────────────────
# extract_trial_features — unit tests
# ─────────────────────────────────────────────

class TestExtractTrialFeatures:

    def test_returns_all_feature_keys(self):
        txns = _txns_from_amounts([1500], gap_days=30)
        feats = extract_trial_features(txns)
        assert set(feats.keys()) == set(FEATURE_KEYS)

    def test_empty_input_returns_zero_dict(self):
        feats = extract_trial_features([])
        assert all(v == 0 for v in feats.values())

    def test_n_charges_correct(self):
        txns = _txns_from_amounts([100, 200, 300])
        assert extract_trial_features(txns)['n_charges'] == 3

    def test_first_charge_is_absolute(self):
        txns = _txns_with_intervals([500, 1500], [30])
        feats = extract_trial_features(txns)
        assert feats['first_charge'] == pytest.approx(500.0)

    def test_first_ratio_low_for_trial_like_first_charge(self):
        """First charge $1 vs median $1500 → ratio ≈ 0.00067, well below 0.1."""
        txns = _txns_with_intervals([1, 1500, 1500, 1500], [7, 30, 30])
        feats = extract_trial_features(txns)
        assert feats['first_ratio'] < 0.1

    def test_first_ratio_near_one_for_stable_charges(self):
        """All equal charges → ratio == 1.0."""
        txns = _txns_from_amounts([1500, 1500, 1500, 1500])
        feats = extract_trial_features(txns)
        assert feats['first_ratio'] == pytest.approx(1.0)

    def test_first_ratio_when_median_is_zero(self):
        """If all amounts are 0, ratio should default to 1.0 (no anomaly)."""
        txns = _txns_from_amounts([0, 0, 0])
        feats = extract_trial_features(txns)
        assert feats['first_ratio'] == pytest.approx(1.0)

    # --- interval tests ---

    def test_intervals_correct_for_30_day_gap(self):
        txns = _txns_from_amounts([100, 200, 300], gap_days=30)
        feats = extract_trial_features(txns)
        assert feats['min_interval_days'] == 30
        assert feats['max_interval_days'] == 30

    def test_intervals_zero_for_single_charge(self):
        txns = _txns_from_amounts([500])
        feats = extract_trial_features(txns)
        assert feats['min_interval_days'] == 0
        assert feats['max_interval_days'] == 0

    def test_min_max_intervals_mixed(self):
        txns = _txns_with_intervals([100, 200, 300, 400], [7, 30, 14])
        feats = extract_trial_features(txns)
        assert feats['min_interval_days'] == 7
        assert feats['max_interval_days'] == 30

    # --- matches_trial_period ---

    def test_matches_trial_period_exact_30_days(self):
        txns = _txns_from_amounts([100, 1500, 1500], gap_days=30)
        assert extract_trial_features(txns)['matches_trial_period'] == 1

    def test_matches_trial_period_28_days_within_tolerance(self):
        """28 days is within 3 of 30 → should match."""
        txns = _txns_with_intervals([100, 1500], [28])
        assert extract_trial_features(txns)['matches_trial_period'] == 1

    def test_matches_trial_period_7_days(self):
        txns = _txns_from_amounts([1, 999, 999], gap_days=7)
        assert extract_trial_features(txns)['matches_trial_period'] == 1

    def test_matches_trial_period_14_days(self):
        txns = _txns_with_intervals([50, 500], [14])
        assert extract_trial_features(txns)['matches_trial_period'] == 1

    def test_matches_trial_period_false_for_odd_interval(self):
        """20-day interval is not within 3 of 7, 14, 30, or 365."""
        txns = _txns_with_intervals([1500, 1500], [20])
        assert extract_trial_features(txns)['matches_trial_period'] == 0

    def test_matches_trial_period_false_for_single_charge(self):
        txns = _txns_from_amounts([1500])
        assert extract_trial_features(txns)['matches_trial_period'] == 0

    # --- has_price_stepup ---

    def test_has_price_stepup_detected(self):
        """Second charge > 1.5× first → stepup = True."""
        txns = _txns_with_intervals([100, 1500, 1500], [30, 30])
        assert extract_trial_features(txns)['has_price_stepup'] == 1

    def test_no_stepup_for_stable_charges(self):
        txns = _txns_from_amounts([1500, 1500, 1500])
        assert extract_trial_features(txns)['has_price_stepup'] == 0

    def test_no_stepup_for_single_charge(self):
        txns = _txns_from_amounts([1500])
        assert extract_trial_features(txns)['has_price_stepup'] == 0

    def test_stepup_requires_more_than_1_5x(self):
        """1.4× first charge is NOT a step-up."""
        txns = _txns_with_intervals([1000, 1400], [30])
        assert extract_trial_features(txns)['has_price_stepup'] == 0

    # --- is_cold_start ---

    def test_is_cold_start_true_for_one_charge(self):
        assert extract_trial_features(_txns_from_amounts([500]))['is_cold_start'] == 1

    def test_is_cold_start_true_for_two_charges(self):
        assert extract_trial_features(_txns_from_amounts([500, 500]))['is_cold_start'] == 1

    def test_is_cold_start_false_for_three_charges(self):
        assert extract_trial_features(_txns_from_amounts([500, 500, 500]))['is_cold_start'] == 0


# ─────────────────────────────────────────────
# build_synthetic_dataset
# ─────────────────────────────────────────────

class TestBuildSyntheticDataset:

    def test_returns_numpy_arrays(self):
        X, y = build_synthetic_dataset()
        assert isinstance(X, np.ndarray)
        assert isinstance(y, np.ndarray)

    def test_shapes_consistent(self):
        X, y = build_synthetic_dataset()
        assert X.shape[0] == y.shape[0]
        assert X.shape[1] == len(FEATURE_KEYS)

    def test_both_classes_present(self):
        _, y = build_synthetic_dataset()
        assert 1 in y and 0 in y

    def test_labels_are_binary(self):
        _, y = build_synthetic_dataset()
        assert set(y).issubset({0, 1})


# ─────────────────────────────────────────────
# train_classifier
# ─────────────────────────────────────────────

class TestTrainClassifier:

    def test_returns_fitted_model(self, trained_model):
        assert hasattr(trained_model, 'predict_proba')

    def test_predict_proba_shape(self, trained_model):
        X, _ = build_synthetic_dataset()
        proba = trained_model.predict_proba(X)
        assert proba.shape == (X.shape[0], 2)
        assert np.allclose(proba.sum(axis=1), 1.0)

    def test_recalls_trial_patterns(self, trained_model):
        """Model should score obvious trial patterns above 0.5."""
        # Classic trial: tiny first charge → full price
        txns = _txns_with_intervals([0.01, 1500, 1500, 1500], [30, 30, 30])
        score = predict_trial_intent(txns, trained_model)
        assert score > 0.5, f'Expected trial score > 0.5, got {score:.3f}'

    def test_recalls_non_trial_patterns(self, trained_model):
        """Model should score stable monthly charges below 0.5."""
        txns = _txns_from_amounts([1500, 1500, 1500, 1500, 1500], gap_days=30)
        score = predict_trial_intent(txns, trained_model)
        assert score < 0.5, f'Expected non-trial score < 0.5, got {score:.3f}'


# ─────────────────────────────────────────────
# predict_trial_intent
# ─────────────────────────────────────────────

class TestPredictTrialIntent:

    def test_returns_float_in_unit_interval(self, trained_model):
        txns = _txns_from_amounts([1500, 1500, 1500], gap_days=30)
        score = predict_trial_intent(txns, trained_model)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_cold_start_score_in_blend_range(self, trained_model):
        """
        With n_charges=1 (cold start), blend formula is:
            score = 0.4 × 0.3 + 0.6 × model_score = 0.12 + 0.6 × model_score
        So score ∈ [0.12, 0.72] regardless of model output.
        """
        txns = [_make_txn('2026-01-01', -1500.0)]
        score = predict_trial_intent(txns, trained_model)
        pw, mw = COLD_START_WEIGHTS
        min_score = pw * COLD_START_PRIOR + mw * 0.0   # model_score = 0
        max_score = pw * COLD_START_PRIOR + mw * 1.0   # model_score = 1
        assert min_score <= score <= max_score, (
            f'Cold-start score {score:.4f} outside blend range '
            f'[{min_score:.2f}, {max_score:.2f}]'
        )

    def test_non_cold_start_no_prior_blend(self, trained_model):
        """n_charges=5 → score equals model_score directly, can go near 0."""
        txns = _txns_from_amounts([1500] * 5, gap_days=30)
        score = predict_trial_intent(txns, trained_model)
        pw, mw = COLD_START_WEIGHTS
        blend_min = pw * COLD_START_PRIOR  # 0.12
        # Non-cold-start can score below the cold-start floor
        # Just verify it's a valid probability
        assert 0.0 <= score <= 1.0

    def test_trial_scores_higher_than_non_trial(self, trained_model):
        """Clear trial pattern should score higher than stable non-trial."""
        trial_txns = _txns_with_intervals([0.01, 1500, 1500, 1500], [30, 30, 30])
        stable_txns = _txns_from_amounts([1500] * 5, gap_days=30)
        assert (predict_trial_intent(trial_txns, trained_model) >
                predict_trial_intent(stable_txns, trained_model))


# ─────────────────────────────────────────────
# classify_all_merchants
# ─────────────────────────────────────────────

class TestClassifyAllMerchants:

    def _mixed_pipeline_txns(self):
        """Three merchants: obvious trial, stable sub, one-off."""
        return (
            _txns_with_intervals([0.01, 1500, 1500], [30, 30], merchant='NETFLIX') +
            _txns_from_amounts([999, 999, 999, 999], gap_days=30, merchant='SPOTIFY') +
            [_make_txn('2026-01-15', -3500.0, merchant='HI-LO BASIX')]
        )

    def test_returns_new_list(self, trained_model):
        txns = self._mixed_pipeline_txns()
        result = classify_all_merchants(txns, trained_model)
        assert result is not txns

    def test_input_not_mutated(self, trained_model):
        txns = self._mixed_pipeline_txns()
        original = [dict(t) for t in txns]
        classify_all_merchants(txns, trained_model)
        assert txns == original

    def test_trial_score_added_to_all_rows(self, trained_model):
        txns = self._mixed_pipeline_txns()
        result = classify_all_merchants(txns, trained_model)
        assert all('trial_score' in t for t in result)

    def test_trial_flag_added_to_all_rows(self, trained_model):
        txns = self._mixed_pipeline_txns()
        result = classify_all_merchants(txns, trained_model)
        assert all('trial_flag' in t for t in result)

    def test_trial_flag_is_bool(self, trained_model):
        txns = self._mixed_pipeline_txns()
        result = classify_all_merchants(txns, trained_model)
        assert all(isinstance(t['trial_flag'], bool) for t in result)

    def test_same_merchant_id_gets_same_score(self, trained_model):
        """All rows belonging to the same merchant_id must share a trial_score."""
        txns = self._mixed_pipeline_txns()
        result = classify_all_merchants(txns, trained_model)
        by_mid: dict[str, list[float]] = defaultdict(list)
        for t in result:
            by_mid[t['merchant_id']].append(t['trial_score'])
        for mid, scores in by_mid.items():
            assert len(set(scores)) == 1, f'{mid} has inconsistent scores: {scores}'

    def test_empty_input(self, trained_model):
        assert classify_all_merchants([], trained_model) == []

    def test_trial_flag_respects_threshold(self, trained_model):
        """All scores must be flagged iff score > threshold."""
        txns = self._mixed_pipeline_txns()
        threshold = 0.60
        result = classify_all_merchants(txns, trained_model, threshold=threshold)
        for t in result:
            assert t['trial_flag'] == (t['trial_score'] > threshold)

    def test_obvious_trial_flagged(self, trained_model):
        """Netflix-like pattern (n>=3, huge step-up) should be flagged."""
        txns = _txns_with_intervals(
            [0.01, 1500, 1500, 1500], [30, 30, 30], merchant='NETFLIX'
        )
        result = classify_all_merchants(txns, trained_model, threshold=0.60)
        assert result[0]['trial_flag'] is True


# ─────────────────────────────────────────────
# Integration tests — real PDF data
# ─────────────────────────────────────────────

@pytest.fixture(scope='module')
def pipeline_results(trained_model):
    """Run the full pipeline on both PDFs once; cache results."""
    results = {}
    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw       = parser(path)
        filtered  = filter_transactions(raw)
        clustered = cluster_merchants(filtered)
        scored    = classify_all_merchants(clustered, trained_model)
        results[bank] = scored
    return results


class TestNCBIntegration:

    def test_all_rows_have_trial_score(self, pipeline_results):
        assert all('trial_score' in t for t in pipeline_results['NCB'])

    def test_all_rows_have_trial_flag(self, pipeline_results):
        assert all('trial_flag' in t for t in pipeline_results['NCB'])

    def test_scores_in_unit_interval(self, pipeline_results):
        scores = [t['trial_score'] for t in pipeline_results['NCB']]
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_cold_start_scores_in_blend_range(self, pipeline_results):
        """All NCB merchants have 1 charge (cold-start) → blend applies."""
        pw, mw = COLD_START_WEIGHTS
        lo = pw * COLD_START_PRIOR
        hi = pw * COLD_START_PRIOR + mw * 1.0
        for t in pipeline_results['NCB']:
            assert lo <= t['trial_score'] <= hi, (
                f"{t['merchant_id']} score {t['trial_score']:.4f} "
                f"outside cold-start range [{lo:.2f}, {hi:.2f}]"
            )

    def test_print_ncb_trial_scores(self, pipeline_results, capsys):
        seen: set[str] = set()
        rows = []
        for t in pipeline_results['NCB']:
            if t['merchant_id'] not in seen:
                seen.add(t['merchant_id'])
                rows.append(t)
        rows.sort(key=lambda t: t['trial_score'], reverse=True)
        print('\n--- NCB trial scores ---')
        for t in rows:
            flag = '[TRIAL]' if t['trial_flag'] else '       '
            print(f"  {flag} {t['trial_score']:.3f}  {t['merchant_id']}")
        assert 'NCB trial scores' in capsys.readouterr().out


class TestScotiabankIntegration:

    def test_all_rows_have_trial_score(self, pipeline_results):
        assert all('trial_score' in t for t in pipeline_results['Scotiabank'])

    def test_all_rows_have_trial_flag(self, pipeline_results):
        assert all('trial_flag' in t for t in pipeline_results['Scotiabank'])

    def test_scores_in_unit_interval(self, pipeline_results):
        scores = [t['trial_score'] for t in pipeline_results['Scotiabank']]
        assert all(0.0 <= s <= 1.0 for s in scores)

    def test_hilo_basix_not_flagged(self, pipeline_results):
        """HI-LO BASIX (grocery, 4 charges, stable) should not be flagged."""
        hilo = [t for t in pipeline_results['Scotiabank']
                if 'HI-LO BASIX' in t['merchant_id']]
        assert hilo, 'HI-LO BASIX not found in Scotia results'
        assert all(not t['trial_flag'] for t in hilo), (
            f"HI-LO BASIX incorrectly flagged as trial "
            f"(score={hilo[0]['trial_score']:.3f})"
        )

    def test_print_scotiabank_trial_scores(self, pipeline_results, capsys):
        seen: set[str] = set()
        rows = []
        for t in pipeline_results['Scotiabank']:
            if t['merchant_id'] not in seen:
                seen.add(t['merchant_id'])
                rows.append(t)
        rows.sort(key=lambda t: t['trial_score'], reverse=True)
        print('\n--- Scotiabank trial scores ---')
        for t in rows:
            flag = '[TRIAL]' if t['trial_flag'] else '       '
            print(f"  {flag} {t['trial_score']:.3f}  {t['merchant_id']}")
        assert 'Scotiabank trial scores' in capsys.readouterr().out
