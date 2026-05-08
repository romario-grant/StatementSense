"""
Statement Sense — Subscription Scorer  (Feature 7.2 — core model)
Computes a composite subscription-confidence score S ∈ [0, 1] for each
merchant using three orthogonal signals:

    S = 0.35 × Stability + 0.40 × Periodicity + 0.25 × Consistency

A merchant is flagged as a confirmed subscription when S ≥ 0.65,
or as a possible subscription when 0.40 ≤ S < 0.65.

Pipeline position:
    pdf_parsers → transaction_filter → merchant_normaliser
      → trial_classifier → currency_normaliser → renewal_predictor
                                                         ↓
                                            subscription_scorer  ← here
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

import numpy as np


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

#: S threshold above which a merchant is classified as a confirmed subscription
CONFIRMED_THRESHOLD: float = 0.65

#: S threshold above which a merchant is classified as a possible subscription
POSSIBLE_THRESHOLD: float = 0.40

#: Canonical billing-cycle lengths in days (weekly → annual)
BILLING_CYCLES: list[int] = [7, 14, 30, 90, 180, 365]

#: Component weights that sum to 1.0
WEIGHTS: dict[str, float] = {
    'stability':   0.35,
    'periodicity': 0.40,
    'consistency': 0.25,
}


# ─────────────────────────────────────────────
# Component scorers
# ─────────────────────────────────────────────

def compute_stability(amounts: list[float]) -> float:
    """
    Measure how consistent the charge amount is across all charges.

    Uses coefficient of variation: CV = σ / μ.
    stability = max(0, 1 − CV)

    A perfectly stable amount (CV = 0) returns 1.0.
    High variance returns a value close to 0.0.

    Special cases
    -------------
    - Single charge  → 1.0  (no variation to measure)
    - Zero mean      → 0.0  (CV undefined; treat as maximally unstable)
    """
    if len(amounts) <= 1:
        return 1.0

    arr  = np.array(amounts, dtype=float)
    mean = float(arr.mean())
    if mean == 0.0:
        return 0.0

    cv = float(arr.std()) / mean      # population std (ddof=0)
    return float(max(0.0, 1.0 - cv))


def compute_periodicity(intervals: list[int],
                        tolerance_days: int = 3) -> float:
    """
    Measure how regularly the charges occur.

    Returns 1.0 if the median interval falls within ``tolerance_days`` of any
    value in ``BILLING_CYCLES`` (7, 14, 30, 90, 180, 365 days).
    Returns 0.0 otherwise (or when no intervals are available).

    Parameters
    ----------
    intervals      : day gaps between consecutive charges (any length ≥ 0)
    tolerance_days : allowed deviation from a canonical cycle (default 3)
    """
    if not intervals:
        return 0.0

    med = float(np.median(intervals))
    for cycle in BILLING_CYCLES:
        if abs(med - cycle) <= tolerance_days:
            return 1.0
    return 0.0


def compute_consistency(n_charges: int, n_months: int) -> float:
    """
    Measure how complete the charge history is relative to the statement window.

    consistency = min(1.0, n_charges / n_months)

    A merchant with one charge per month over the full window scores 1.0.
    Fewer charges → lower score, proportionally.

    Returns 0.0 when n_months is 0 (undefined window).
    """
    if n_months == 0:
        return 0.0
    return min(1.0, n_charges / n_months)


# ─────────────────────────────────────────────
# Merchant scoring
# ─────────────────────────────────────────────

def score_merchant(
    merchant_transactions: list[dict],
    n_months: int = 1,
) -> dict:
    """
    Compute the composite score S for ONE merchant group.

    Parameters
    ----------
    merchant_transactions : all transactions for ONE merchant_id
    n_months              : number of months in the statement window
                            (used for consistency calculation)

    Returns
    -------
    dict with keys:
        stability, periodicity, consistency — component scores [0, 1]
        subscription_score                  — composite S [0, 1]
        subscription_flag                   — True if S ≥ CONFIRMED_THRESHOLD
        possible_flag                       — True if POSSIBLE_THRESHOLD ≤ S < CONFIRMED_THRESHOLD
        n_charges                           — number of charges
        median_interval_days                — median day gap (0 if single charge)
    """
    sorted_txns = sorted(merchant_transactions, key=lambda t: t['date'])
    amounts     = [abs(float(t['amount'])) for t in sorted_txns]
    dates       = [date.fromisoformat(t['date']) for t in sorted_txns]
    intervals   = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

    stability   = compute_stability(amounts)
    periodicity = compute_periodicity(intervals)
    consistency = compute_consistency(len(amounts), n_months)

    S = (WEIGHTS['stability']   * stability
         + WEIGHTS['periodicity'] * periodicity
         + WEIGHTS['consistency'] * consistency)

    median_interval = int(np.median(intervals)) if intervals else 0

    return {
        'stability':            round(stability,   4),
        'periodicity':          round(periodicity, 4),
        'consistency':          round(consistency, 4),
        'subscription_score':   round(S, 4),
        'subscription_flag':    bool(S >= CONFIRMED_THRESHOLD),
        'possible_flag':        bool(POSSIBLE_THRESHOLD <= S < CONFIRMED_THRESHOLD),
        'n_charges':            len(amounts),
        'median_interval_days': median_interval,
    }


# ─────────────────────────────────────────────
# Batch scoring
# ─────────────────────────────────────────────

def score_all_merchants(
    transactions: list[dict],
    n_months: int = 1,
) -> list[dict]:
    """
    Stamp subscription scoring fields onto every transaction.

    Groups by merchant_id, calls score_merchant once per group,
    then fans the result back out to every row in that group.

    Fields added to each transaction
    ---------------------------------
    subscription_score, subscription_flag, possible_flag,
    stability, periodicity, consistency

    Returns a new list of dicts; input is not mutated.
    """
    if not transactions:
        return []

    result  = [dict(t) for t in transactions]
    groups: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(result):
        groups[t['merchant_id']].append(i)

    for mid, indices in groups.items():
        group_txns = [result[i] for i in indices]
        sc         = score_merchant(group_txns, n_months)
        for i in indices:
            result[i]['subscription_score'] = sc['subscription_score']
            result[i]['subscription_flag']  = sc['subscription_flag']
            result[i]['possible_flag']      = sc['possible_flag']
            result[i]['stability']          = sc['stability']
            result[i]['periodicity']        = sc['periodicity']
            result[i]['consistency']        = sc['consistency']

    return result


# ─────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────

if __name__ == '__main__':
    import os
    from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
    from transaction_filter import filter_transactions
    from merchant_normaliser import cluster_merchants
    from trial_classifier import (build_synthetic_dataset, train_classifier,
                                   classify_all_merchants)
    from currency_normaliser import normalise_transactions
    from renewal_predictor import predict_all_merchants

    NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
    SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')
    SYNTH_PATH  = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Documents\Capstone'
                   r'\StatementSense_Synthetic_5000_Group21 (1).xlsx')

    REFERENCE_DATE = '2026-04-25'

    X, y  = build_synthetic_dataset()
    model = train_classifier(X, y)

    # ── Real PDFs (1 month) ──────────────────────────────────────────────
    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw       = parser(path)
        filtered  = filter_transactions(raw)
        clustered = cluster_merchants(filtered)
        scored_tc = classify_all_merchants(clustered, model)
        normed    = normalise_transactions(scored_tc)
        predicted = predict_all_merchants(normed, reference_date=REFERENCE_DATE)
        scored    = score_all_merchants(predicted, n_months=1)

        # Deduplicate
        seen: set[str] = set()
        rows: list[dict] = []
        for t in scored:
            mid = t['merchant_id']
            if mid not in seen:
                seen.add(mid)
                rows.append(t)
        rows.sort(key=lambda t: t['subscription_score'], reverse=True)

        confirmed = sum(1 for r in rows if r['subscription_flag'])
        possible  = sum(1 for r in rows if r['possible_flag'])

        W = 36
        print(f'\n{"=" * 85}')
        print(f'  {bank}  (n_months=1)  |  {len(rows)} merchants  |  '
              f'{confirmed} confirmed  |  {possible} possible')
        print(f'{"=" * 85}')
        print(f'  {"Merchant":<{W}}  {"Score":>6}  {"Stab":>5}  {"Per":>5}  '
              f'{"Con":>5}  {"Flag"}')
        print(f'  {"-"*W}  {"-"*6}  {"-"*5}  {"-"*5}  {"-"*5}  {"-"*10}')
        for r in rows:
            flag = '[CONFIRMED]' if r['subscription_flag'] else \
                   '[POSSIBLE] ' if r['possible_flag']      else '           '
            print(f'  {r["merchant_id"]:<{W}}  {r["subscription_score"]:>6.4f}  '
                  f'{r["stability"]:>5.2f}  {r["periodicity"]:>5.2f}  '
                  f'{r["consistency"]:>5.2f}  {flag}')

    # ── Synthetic dataset (9 months) ─────────────────────────────────────
    if os.path.exists(SYNTH_PATH):
        from evaluation import load_synthetic_dataset
        synth_txns = load_synthetic_dataset(SYNTH_PATH)
        scored_s   = score_all_merchants(synth_txns, n_months=9)

        seen_s: set[str] = set()
        rows_s: list[dict] = []
        for t in scored_s:
            mid = t['merchant_id']
            if mid not in seen_s:
                seen_s.add(mid)
                rows_s.append(t)
        rows_s.sort(key=lambda t: t['subscription_score'], reverse=True)

        confirmed_s = sum(1 for r in rows_s if r['subscription_flag'])
        possible_s  = sum(1 for r in rows_s if r['possible_flag'])

        print(f'\n{"=" * 85}')
        print(f'  Synthetic Dataset  (n_months=9)  |  {len(rows_s)} merchants  |  '
              f'{confirmed_s} confirmed  |  {possible_s} possible')
        print(f'{"=" * 85}')
        print(f'  {"Merchant":<{W}}  {"Score":>6}  {"Stab":>5}  {"Per":>5}  '
              f'{"Con":>5}  {"Label":<15}  {"Flag"}')
        print(f'  {"-"*W}  {"-"*6}  {"-"*5}  {"-"*5}  {"-"*5}  {"-"*15}  {"-"*10}')
        for r in rows_s[:40]:   # cap output to top 40
            flag  = '[CONFIRMED]' if r['subscription_flag'] else \
                    '[POSSIBLE] ' if r['possible_flag']      else '           '
            label = r.get('label', '?')
            print(f'  {r["merchant_id"]:<{W}}  {r["subscription_score"]:>6.4f}  '
                  f'{r["stability"]:>5.2f}  {r["periodicity"]:>5.2f}  '
                  f'{r["consistency"]:>5.2f}  {label:<15}  {flag}')
    else:
        print(f'\n[SKIP] Synthetic dataset not found: {SYNTH_PATH}')
