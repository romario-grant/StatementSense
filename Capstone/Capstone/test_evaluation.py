"""
Tests for evaluation.py  (Phase 5 CRISP-DM Evaluation)

Unit tests use small synthetic transaction lists with known labels.
Integration tests require the real synthetic Excel dataset.
"""

import os
import pytest

from subscription_scorer import CONFIRMED_THRESHOLD

SYNTH_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
              r'Vocational Training\Documents\Capstone'
              r'\StatementSense_Synthetic_5000_Group21 (1).xlsx')

#: Required keys in every evaluate_model result dict
METRIC_KEYS = {
    'true_positives', 'false_positives',
    'true_negatives', 'false_negatives',
    'precision', 'recall', 'f1_score', 'accuracy',
    'threshold_used', 'n_merchants', 'n_transactions',
}


# ─────────────────────────────────────────────
# Helpers — mini labelled datasets
# ─────────────────────────────────────────────

def _make_labelled_txns(specs: list[tuple[str, str, str, float, list[int]]]) -> list[dict]:
    """
    Build a minimal labelled transaction list.

    specs : list of (merchant_id, label, start_date, amount, gap_list)
    """
    from datetime import date, timedelta
    txns = []
    for mid, label, start, amount, gaps in specs:
        d = date.fromisoformat(start)
        dates = [d.isoformat()]
        for g in gaps:
            d += timedelta(days=g)
            dates.append(d.isoformat())
        for dt in dates:
            txns.append({
                'merchant_id': mid,
                'date':        dt,
                'amount':      -abs(amount),
                'label':       label,
                'description': f'charge {mid}',
                'bank':        'TEST',
                'currency':    'JMD',
                'balance':     None,
                'source_file': 'test',
            })
    return txns


def _confirmed_subscription_txns() -> list[dict]:
    """A dataset with one clear subscription and one non-subscription."""
    return _make_labelled_txns([
        # Netflix — 9 monthly charges at 1499 JMD
        ('NETFLIX', 'subscription', '2025-07-01', 1499.0, [30] * 8),
        # Hardware store — 2 random charges
        ('HARDWARE', 'non-subscription', '2025-08-10', 5000.0, [45]),
    ])


# ─────────────────────────────────────────────
# load_synthetic_dataset — unit-level (requires Excel)
# ─────────────────────────────────────────────

@pytest.fixture(scope='module')
def synthetic_txns():
    if not os.path.exists(SYNTH_PATH):
        pytest.skip(f'Synthetic dataset not found: {SYNTH_PATH}')
    from evaluation import load_synthetic_dataset
    return load_synthetic_dataset(SYNTH_PATH)


class TestLoadSyntheticDataset:

    def test_returns_list(self, synthetic_txns):
        assert isinstance(synthetic_txns, list)

    def test_nonempty(self, synthetic_txns):
        assert len(synthetic_txns) > 0

    def test_each_dict_has_required_keys(self, synthetic_txns):
        required = {'merchant_id', 'date', 'amount', 'bank',
                    'label', 'currency', 'description', 'balance', 'source_file'}
        for t in synthetic_txns[:20]:
            assert required.issubset(t.keys()), \
                f'Missing keys in: {set(t.keys())}'

    def test_dates_are_iso_strings(self, synthetic_txns):
        from datetime import date
        for t in synthetic_txns[:50]:
            # Should not raise
            date.fromisoformat(t['date'])

    def test_labels_are_valid(self, synthetic_txns):
        valid = {'subscription', 'trial', 'non-subscription'}
        for t in synthetic_txns[:100]:
            assert t['label'] in valid, f'Unexpected label: {t["label"]}'

    def test_amounts_are_numeric(self, synthetic_txns):
        for t in synthetic_txns[:50]:
            assert isinstance(t['amount'], (int, float))

    def test_merchant_id_is_string(self, synthetic_txns):
        for t in synthetic_txns[:50]:
            assert isinstance(t['merchant_id'], str)
            assert len(t['merchant_id']) > 0


# ─────────────────────────────────────────────
# evaluate_model — unit tests (no Excel needed)
# ─────────────────────────────────────────────

class TestEvaluateModel:

    def _run(self, threshold=CONFIRMED_THRESHOLD, n_months=9):
        from evaluation import evaluate_model
        txns = _confirmed_subscription_txns()
        return evaluate_model(txns, n_months=n_months, threshold=threshold)

    def test_returns_all_required_keys(self):
        result = self._run()
        assert METRIC_KEYS.issubset(result.keys())

    def test_metrics_are_floats_in_0_to_1(self):
        result = self._run()
        for key in ('precision', 'recall', 'f1_score', 'accuracy'):
            assert 0.0 <= result[key] <= 1.0, f'{key} = {result[key]} out of [0,1]'

    def test_confusion_matrix_sums_to_n_merchants(self):
        result = self._run()
        total = (result['true_positives'] + result['false_positives']
                 + result['true_negatives'] + result['false_negatives'])
        assert total == result['n_merchants']

    def test_n_merchants_correct(self):
        # Mini dataset has 2 unique merchants
        result = self._run()
        assert result['n_merchants'] == 2

    def test_n_transactions_correct(self):
        txns = _confirmed_subscription_txns()
        from evaluation import evaluate_model
        result = evaluate_model(txns, n_months=9)
        assert result['n_transactions'] == len(txns)

    def test_threshold_used_stored(self):
        result = self._run(threshold=0.70)
        assert result['threshold_used'] == pytest.approx(0.70)

    def test_high_threshold_catches_only_strong_subscriptions(self):
        # At threshold=0.99, almost nothing should be flagged → few FP
        from evaluation import evaluate_model
        txns   = _confirmed_subscription_txns()
        result = evaluate_model(txns, n_months=9, threshold=0.99)
        # With very high threshold, fp should be ≤ fp at threshold=0.65
        result_normal = evaluate_model(txns, n_months=9, threshold=0.65)
        assert result['false_positives'] <= result_normal['false_positives']

    def test_low_threshold_flags_more_merchants(self):
        # At threshold=0.01, everything gets flagged → higher recall
        from evaluation import evaluate_model
        txns          = _confirmed_subscription_txns()
        result_low    = evaluate_model(txns, n_months=9, threshold=0.01)
        result_normal = evaluate_model(txns, n_months=9, threshold=0.65)
        assert result_low['recall'] >= result_normal['recall']


# ─────────────────────────────────────────────
# print_evaluation_report
# ─────────────────────────────────────────────

class TestPrintEvaluationReport:

    def test_runs_without_error(self, capsys):
        from evaluation import evaluate_model, print_evaluation_report
        txns    = _confirmed_subscription_txns()
        metrics = evaluate_model(txns, n_months=9)
        print_evaluation_report(metrics)           # must not raise
        out = capsys.readouterr().out
        assert 'CRISP-DM' in out

    def test_contains_confusion_matrix(self, capsys):
        from evaluation import evaluate_model, print_evaluation_report
        txns    = _confirmed_subscription_txns()
        metrics = evaluate_model(txns, n_months=9)
        print_evaluation_report(metrics)
        out = capsys.readouterr().out
        assert 'Confusion Matrix' in out

    def test_contains_precision_recall(self, capsys):
        from evaluation import evaluate_model, print_evaluation_report
        txns    = _confirmed_subscription_txns()
        metrics = evaluate_model(txns, n_months=9)
        print_evaluation_report(metrics)
        out = capsys.readouterr().out
        assert 'Precision' in out
        assert 'Recall' in out


# ─────────────────────────────────────────────
# threshold_analysis
# ─────────────────────────────────────────────

class TestThresholdAnalysis:

    def _run_analysis(self, thresholds=None):
        from evaluation import threshold_analysis
        txns = _confirmed_subscription_txns()
        return threshold_analysis(txns, n_months=9, thresholds=thresholds)

    def test_returns_one_result_per_threshold(self):
        thresholds = [0.40, 0.50, 0.60, 0.70, 0.80]
        results    = self._run_analysis(thresholds=thresholds)
        assert len(results) == len(thresholds)

    def test_default_thresholds_are_13(self):
        results = self._run_analysis()
        assert len(results) == 13

    def test_each_result_has_metric_keys(self):
        for r in self._run_analysis():
            assert METRIC_KEYS.issubset(r.keys())

    def test_threshold_stored_in_each_result(self):
        thresholds = [0.40, 0.60, 0.80]
        results    = self._run_analysis(thresholds=thresholds)
        stored     = [r['threshold_used'] for r in results]
        assert stored == pytest.approx(thresholds)

    def test_higher_threshold_does_not_increase_recall(self):
        """Recall should be non-increasing as threshold rises."""
        results = self._run_analysis()
        recalls = [r['recall'] for r in results]
        for i in range(len(recalls) - 1):
            assert recalls[i] >= recalls[i + 1] - 1e-9, \
                f'Recall rose from {recalls[i]:.4f} to {recalls[i+1]:.4f}'

    def test_lower_threshold_flags_more_or_equal_merchants(self):
        """Total flagged = TP + FP; must be non-decreasing as threshold falls."""
        results = self._run_analysis()
        results_rev = list(reversed(results))      # high → low threshold
        for i in range(len(results_rev) - 1):
            flagged_high = results_rev[i]['true_positives'] + results_rev[i]['false_positives']
            flagged_low  = results_rev[i + 1]['true_positives'] + results_rev[i + 1]['false_positives']
            assert flagged_low >= flagged_high, \
                f'Flagged count decreased as threshold dropped'


# ─────────────────────────────────────────────
# Integration — full evaluation on real dataset
# ─────────────────────────────────────────────

class TestIntegrationEvaluation:

    def test_evaluate_model_on_synthetic_dataset(self, synthetic_txns, capsys):
        from evaluation import evaluate_model, print_evaluation_report
        metrics = evaluate_model(synthetic_txns, n_months=9, threshold=0.65)
        print_evaluation_report(metrics)

        assert metrics['n_merchants'] > 0
        assert 0.0 <= metrics['f1_score'] <= 1.0
        out = capsys.readouterr().out
        assert 'CRISP-DM' in out

    def test_threshold_analysis_on_synthetic_dataset(self, synthetic_txns, capsys):
        from evaluation import threshold_analysis
        results = threshold_analysis(synthetic_txns, n_months=9)

        assert len(results) == 13

        print(f'\n{"─" * 62}')
        print(f'  Threshold Analysis on Synthetic Dataset')
        print(f'{"─" * 62}')
        print(f'  {"Threshold":>10}  {"Precision":>10}  {"Recall":>8}  '
              f'{"F1":>8}  {"Accuracy":>9}')
        print(f'  {"─"*10}  {"─"*10}  {"─"*8}  {"─"*8}  {"─"*9}')
        for r in results:
            marker = ' ◄' if r['threshold_used'] == 0.65 else ''
            print(f'  {r["threshold_used"]:>10.2f}  {r["precision"]:>10.4f}  '
                  f'{r["recall"]:>8.4f}  {r["f1_score"]:>8.4f}  '
                  f'{r["accuracy"]:>9.4f}{marker}')
        print(f'{"─" * 62}')

        assert 'Threshold Analysis' in capsys.readouterr().out

    def test_precision_generally_increases_with_threshold(self, synthetic_txns):
        """Precision at threshold 0.80 should be ≥ precision at 0.40."""
        from evaluation import evaluate_model
        low  = evaluate_model(synthetic_txns, n_months=9, threshold=0.40)
        high = evaluate_model(synthetic_txns, n_months=9, threshold=0.80)
        assert high['precision'] >= low['precision']

    def test_recall_generally_decreases_with_threshold(self, synthetic_txns):
        """Recall at threshold 0.40 should be ≥ recall at 0.80."""
        from evaluation import evaluate_model
        low  = evaluate_model(synthetic_txns, n_months=9, threshold=0.40)
        high = evaluate_model(synthetic_txns, n_months=9, threshold=0.80)
        assert low['recall'] >= high['recall']
