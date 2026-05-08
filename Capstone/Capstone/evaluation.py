"""
Statement Sense — CRISP-DM Phase 5 Evaluation  (evaluation.py)
Loads the synthetic labelled dataset, runs the subscription scorer,
and computes standard binary-classification metrics against ground truth.

Ground truth mapping
--------------------
label == 'subscription'     → positive class (1)
label == 'trial'            → positive class (1)
label == 'non-subscription' → negative class (0)

Evaluation is per unique merchant_id, since subscription_score / flag is
a merchant-level prediction (all transactions in a group share the same flag).
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime

import openpyxl

from subscription_scorer import score_all_merchants, CONFIRMED_THRESHOLD


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

#: Sheet name in the synthetic dataset workbook
_SHEET_NAME = 'Transaction Dataset'

#: Labels treated as the positive class
_POSITIVE_LABELS = {'subscription', 'trial'}


# ─────────────────────────────────────────────
# Dataset loading
# ─────────────────────────────────────────────

def load_synthetic_dataset(filepath: str) -> list[dict]:
    """
    Read the Transaction Dataset sheet from the synthetic Excel workbook.

    Column mapping
    --------------
    resolved_name  → merchant_id
    amount_jmd     → amount
    raw_descriptor → description
    date           → date  (ISO string 'YYYY-MM-DD')
    label          → label
    bank           → bank
    account        → (discarded — not used downstream)
    'JMD'          → currency
    filepath       → source_file
    None           → balance

    Parameters
    ----------
    filepath : absolute path to the .xlsx workbook

    Returns
    -------
    list of transaction dicts, one per row (header excluded)
    """
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
    ws = wb[_SHEET_NAME]

    rows_iter = ws.iter_rows(values_only=True)

    # Row 1 is a title banner — skip it; row 2 contains actual column headers
    next(rows_iter)
    raw_headers = next(rows_iter)
    headers = [str(h).strip() if h is not None else '' for h in raw_headers]

    transactions: list[dict] = []
    for row in rows_iter:
        if all(v is None for v in row):
            continue
        r = dict(zip(headers, row))

        # Resolve date — arrives as ISO string ('YYYY-MM-DD') in this workbook
        raw_date = r.get('Date', r.get('date', ''))
        if isinstance(raw_date, (datetime, date)):
            date_str = raw_date.strftime('%Y-%m-%d') \
                       if isinstance(raw_date, datetime) \
                       else raw_date.isoformat()
        else:
            date_str = str(raw_date).strip()
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'):
                try:
                    date_str = datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
                    break
                except ValueError:
                    pass

        # Amount (JMD) — signed; negative = debit
        raw_amount = r.get('Amount (JMD)', r.get('amount_jmd', 0)) or 0
        try:
            amount = float(raw_amount)
        except (TypeError, ValueError):
            amount = 0.0

        merchant_id = str(r.get('Resolved Name (alias lookup)',
                                r.get('resolved_name', 'UNKNOWN'))).strip()
        description = str(r.get('Raw Descriptor (on statement)',
                                r.get('raw_descriptor', ''))).strip()
        label    = str(r.get('Label (Ground Truth)', r.get('label', ''))).strip().lower()
        bank     = str(r.get('Bank', r.get('bank', ''))).strip()
        currency = str(r.get('Currency', 'JMD')).strip() or 'JMD'
        raw_bal  = r.get('Balance (JMD)', r.get('balance', None))
        balance  = float(raw_bal) if raw_bal is not None else None

        transactions.append({
            'merchant_id': merchant_id,
            'date':        date_str,
            'amount':      amount,
            'description': description,
            'label':       label,
            'bank':        bank,
            'currency':    currency,
            'balance':     balance,
            'source_file': filepath,
        })

    wb.close()
    return transactions


# ─────────────────────────────────────────────
# Per-merchant ground truth
# ─────────────────────────────────────────────

def _merchant_ground_truth(transactions: list[dict]) -> dict[str, int]:
    """
    Return a dict mapping merchant_id → 1 (positive) or 0 (negative).

    Uses the majority label across all transactions for that merchant.
    In a well-formed synthetic dataset every merchant has a single label,
    so majority vote always resolves cleanly.
    """
    label_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for t in transactions:
        label_counts[t['merchant_id']][t.get('label', 'non-subscription')] += 1

    truth: dict[str, int] = {}
    for mid, counts in label_counts.items():
        majority_label = max(counts, key=counts.__getitem__)
        truth[mid] = 1 if majority_label in _POSITIVE_LABELS else 0
    return truth


# ─────────────────────────────────────────────
# Model evaluation
# ─────────────────────────────────────────────

def evaluate_model(
    transactions: list[dict],
    n_months: int = 9,
    threshold: float = CONFIRMED_THRESHOLD,
) -> dict:
    """
    Run the subscription scorer and compare predictions to ground truth.

    Evaluation is at the merchant level (one prediction per merchant_id).

    Parameters
    ----------
    transactions : labelled transaction list from load_synthetic_dataset
    n_months     : statement window length for consistency calculation
    threshold    : subscription_score cut-off for a positive prediction

    Returns
    -------
    dict with keys:
        true_positives, false_positives, true_negatives, false_negatives,
        precision, recall, f1_score, accuracy,
        threshold_used, n_merchants, n_transactions
    """
    scored = score_all_merchants(transactions, n_months=n_months)
    truth  = _merchant_ground_truth(scored)

    # One representative row per merchant (for score lookup)
    seen: set[str] = set()
    merchant_rows: list[dict] = []
    for t in scored:
        mid = t['merchant_id']
        if mid not in seen:
            seen.add(mid)
            merchant_rows.append(t)

    tp = fp = tn = fn = 0
    for row in merchant_rows:
        mid       = row['merchant_id']
        predicted = int(row['subscription_score'] >= threshold)
        actual    = truth.get(mid, 0)

        if predicted == 1 and actual == 1:
            tp += 1
        elif predicted == 1 and actual == 0:
            fp += 1
        elif predicted == 0 and actual == 0:
            tn += 1
        else:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)
    accuracy  = (tp + tn) / len(merchant_rows) if merchant_rows else 0.0

    return {
        'true_positives':  tp,
        'false_positives': fp,
        'true_negatives':  tn,
        'false_negatives': fn,
        'precision':       round(precision, 4),
        'recall':          round(recall,    4),
        'f1_score':        round(f1,        4),
        'accuracy':        round(accuracy,  4),
        'threshold_used':  threshold,
        'n_merchants':     len(merchant_rows),
        'n_transactions':  len(transactions),
    }


# ─────────────────────────────────────────────
# Report printing
# ─────────────────────────────────────────────

def print_evaluation_report(metrics: dict) -> None:
    """
    Print a formatted CRISP-DM Phase 5 evaluation report with confusion matrix.
    """
    tp = metrics['true_positives']
    fp = metrics['false_positives']
    tn = metrics['true_negatives']
    fn = metrics['false_negatives']

    bar = '═' * 58

    print(f'\n{bar}')
    print(f'  CRISP-DM Phase 5 — Subscription Model Evaluation')
    print(f'{bar}')
    print(f'  Merchants evaluated : {metrics["n_merchants"]}')
    print(f'  Transactions loaded : {metrics["n_transactions"]}')
    print(f'  Score threshold     : {metrics["threshold_used"]:.2f}')
    print()
    print(f'  Confusion Matrix')
    print(f'  {"":20}  {"Pred +":>10}  {"Pred −":>10}')
    print(f'  {"─"*20}  {"─"*10}  {"─"*10}')
    print(f'  {"Actual + (sub/trial)":<20}  {tp:>10}  {fn:>10}')
    print(f'  {"Actual − (non-sub)":<20}  {fp:>10}  {tn:>10}')
    print()
    print(f'  Precision  : {metrics["precision"]:.4f}  '
          f'  (of flagged merchants, how many are real subscriptions)')
    print(f'  Recall     : {metrics["recall"]:.4f}  '
          f'  (of real subscriptions, how many were caught)')
    print(f'  F1 Score   : {metrics["f1_score"]:.4f}')
    print(f'  Accuracy   : {metrics["accuracy"]:.4f}')
    print(f'{bar}')


# ─────────────────────────────────────────────
# Threshold analysis
# ─────────────────────────────────────────────

def threshold_analysis(
    transactions: list[dict],
    n_months: int = 9,
    thresholds: list[float] | None = None,
) -> list[dict]:
    """
    Run evaluate_model at multiple thresholds to show precision/recall tradeoff.

    Parameters
    ----------
    transactions : labelled transaction list from load_synthetic_dataset
    n_months     : statement window length passed to score_all_merchants
    thresholds   : thresholds to evaluate (default: 0.30 to 0.90 in 0.05 steps)

    Returns
    -------
    list of metric dicts, one per threshold, in threshold order
    """
    if thresholds is None:
        thresholds = [round(0.30 + i * 0.05, 2) for i in range(13)]   # 0.30 … 0.90

    # Score once; evaluate_model re-scores internally so score here first to avoid
    # re-running clustering at every threshold — cache scored transactions
    scored = score_all_merchants(transactions, n_months=n_months)
    truth  = _merchant_ground_truth(scored)

    # One row per merchant
    seen: set[str] = set()
    merchant_rows: list[dict] = []
    for t in scored:
        mid = t['merchant_id']
        if mid not in seen:
            seen.add(mid)
            merchant_rows.append(t)

    results: list[dict] = []
    for thr in thresholds:
        tp = fp = tn = fn = 0
        for row in merchant_rows:
            mid       = row['merchant_id']
            predicted = int(row['subscription_score'] >= thr)
            actual    = truth.get(mid, 0)
            if predicted == 1 and actual == 1:
                tp += 1
            elif predicted == 1 and actual == 0:
                fp += 1
            elif predicted == 0 and actual == 0:
                tn += 1
            else:
                fn += 1

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1        = (2 * precision * recall / (precision + recall)
                     if (precision + recall) > 0 else 0.0)
        accuracy  = (tp + tn) / len(merchant_rows) if merchant_rows else 0.0

        results.append({
            'true_positives':  tp,
            'false_positives': fp,
            'true_negatives':  tn,
            'false_negatives': fn,
            'precision':       round(precision, 4),
            'recall':          round(recall,    4),
            'f1_score':        round(f1,        4),
            'accuracy':        round(accuracy,  4),
            'threshold_used':  thr,
            'n_merchants':     len(merchant_rows),
            'n_transactions':  len(transactions),
        })

    return results


# ─────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────

if __name__ == '__main__':
    SYNTH_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                  r'Vocational Training\Documents\Capstone'
                  r'\StatementSense_Synthetic_5000_Group21 (1).xlsx')

    if not os.path.exists(SYNTH_PATH):
        print(f'[SKIP] Synthetic dataset not found:\n       {SYNTH_PATH}')
        raise SystemExit(0)

    print(f'Loading synthetic dataset from:\n  {SYNTH_PATH}\n')
    txns = load_synthetic_dataset(SYNTH_PATH)
    print(f'Loaded {len(txns)} transactions')

    # ── Main evaluation at threshold = 0.65 ─────────────────────────────
    metrics = evaluate_model(txns, n_months=9, threshold=0.65)
    print_evaluation_report(metrics)

    # ── Threshold sweep ──────────────────────────────────────────────────
    results = threshold_analysis(txns, n_months=9)

    print(f'\n{"─" * 62}')
    print(f'  Threshold Analysis  (precision / recall tradeoff)')
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
