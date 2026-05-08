"""
Statement Sense — Renewal Predictor  (Feature 7.3 — renewal half)
Predicts WHEN the next charge for each subscription merchant will hit,
so alerts can be sent 3 days in advance.

Design goals
------------
- Robust to billing-date drift (subscriptions often shift 1–3 days each cycle)
- Handles missing charges (payment failures, plan pauses)
- Degrades gracefully when charge history is sparse (cold start)

Pipeline position:
    pdf_parsers → transaction_filter → merchant_normaliser
      → trial_classifier → currency_normaliser
                                      ↓
                            renewal_predictor  ← here
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

import numpy as np


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

#: Days to assume between charges when only one charge exists (cold start)
COLD_START_PRIOR_DAYS: int = 30

#: How many days before the predicted charge to fire an alert
ALERT_LEAD_DAYS: int = 3

#: Minimum number of intervals required for 'high' confidence
HIGH_CONFIDENCE_MIN_INTERVALS: int = 3


# ─────────────────────────────────────────────
# Interval computation
# ─────────────────────────────────────────────

def compute_intervals(transactions: list[dict]) -> list[int]:
    """
    Compute day gaps between consecutive charges for one merchant.

    Parameters
    ----------
    transactions : all transactions for ONE merchant_id (any order)

    Returns
    -------
    list of int  — day gaps sorted chronologically;
                   empty list if fewer than 2 transactions.
    """
    if len(transactions) < 2:
        return []

    sorted_txns = sorted(transactions, key=lambda t: t['date'])
    dates = [date.fromisoformat(t['date']) for t in sorted_txns]
    return [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]


# ─────────────────────────────────────────────
# Single-merchant prediction
# ─────────────────────────────────────────────

def predict_next_charge(
    merchant_transactions: list[dict],
    reference_date: str | None = None,
) -> dict:
    """
    Predict when the next charge will occur for one merchant.

    Confidence tiers
    ----------------
    - 0 intervals (1 charge)   → cold-start prior (30 days), confidence = 'low'
    - 1–2 intervals            → median interval,             confidence = 'medium'
    - 3+ intervals             → IQR-robust median,           confidence = 'high'

    Parameters
    ----------
    merchant_transactions : all transactions for ONE merchant_id
    reference_date        : ISO date string for computing days_until
                            (defaults to today)

    Returns
    -------
    dict with keys:
        last_charge_date      — ISO date of most recent charge
        median_interval_days  — predicted cycle length in days
        next_charge_date      — ISO date of predicted next charge
        confidence_band_days  — ± days around prediction (0 if < 4 intervals)
        confidence            — 'low' | 'medium' | 'high'
        days_until            — days from reference_date to next_charge_date
                                (negative = already overdue)
        alert_date            — ISO date to fire the advance alert
        is_cold_start         — True if prediction is based on cold-start prior
    """
    ref = date.fromisoformat(reference_date) if reference_date else date.today()

    sorted_txns = sorted(merchant_transactions, key=lambda t: t['date'])
    last_date   = date.fromisoformat(sorted_txns[-1]['date'])
    intervals   = compute_intervals(sorted_txns)
    n           = len(intervals)

    is_cold_start = (n == 0)

    if n == 0:
        median_interval      = COLD_START_PRIOR_DAYS
        confidence           = 'low'
        confidence_band_days = 0
    elif n <= 2:
        median_interval      = int(np.median(intervals))
        confidence           = 'medium'
        confidence_band_days = 0
    else:
        arr            = np.array(intervals, dtype=float)
        median_interval = int(np.median(arr))
        confidence      = 'high'
        if n >= 4:
            q1, q3               = np.percentile(arr, [25, 75])
            confidence_band_days = round(1.5 * (q3 - q1))
        else:
            confidence_band_days = 0

    next_charge_date = last_date + timedelta(days=median_interval)
    days_until       = (next_charge_date - ref).days
    alert_date       = next_charge_date - timedelta(days=ALERT_LEAD_DAYS)

    return {
        'last_charge_date':     last_date.isoformat(),
        'median_interval_days': median_interval,
        'next_charge_date':     next_charge_date.isoformat(),
        'confidence_band_days': confidence_band_days,
        'confidence':           confidence,
        'days_until':           days_until,
        'alert_date':           alert_date.isoformat(),
        'is_cold_start':        is_cold_start,
    }


# ─────────────────────────────────────────────
# Batch prediction
# ─────────────────────────────────────────────

def predict_all_merchants(
    transactions: list[dict],
    reference_date: str | None = None,
) -> list[dict]:
    """
    Stamp renewal prediction fields onto every transaction.

    Groups by merchant_id, calls predict_next_charge once per group,
    then fans the result back out to every row in that group.

    Fields added to each transaction
    ---------------------------------
    last_charge_date, next_charge_date, days_until, confidence,
    confidence_band_days, alert_date, is_cold_start

    Returns a new list of dicts; input is not mutated.
    """
    if not transactions:
        return []

    result = [dict(t) for t in transactions]

    groups: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(result):
        groups[t['merchant_id']].append(i)

    for mid, indices in groups.items():
        group_txns = [result[i] for i in indices]
        pred       = predict_next_charge(group_txns, reference_date)
        for i in indices:
            result[i]['last_charge_date']     = pred['last_charge_date']
            result[i]['next_charge_date']     = pred['next_charge_date']
            result[i]['days_until']           = pred['days_until']
            result[i]['confidence']           = pred['confidence']
            result[i]['confidence_band_days'] = pred['confidence_band_days']
            result[i]['alert_date']           = pred['alert_date']
            result[i]['is_cold_start']        = pred['is_cold_start']

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
    from currency_normaliser import normalise_transactions

    NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
    SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')

    REFERENCE_DATE = '2026-04-25'

    X, y  = build_synthetic_dataset()
    model = train_classifier(X, y)

    all_predictions: list[dict] = []

    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw       = parser(path)
        filtered  = filter_transactions(raw)
        clustered = cluster_merchants(filtered)
        scored    = classify_all_merchants(clustered, model)
        normed    = normalise_transactions(scored)
        predicted = predict_all_merchants(normed, reference_date=REFERENCE_DATE)

        # One representative row per merchant_id
        seen: set[str] = set()
        for t in predicted:
            mid = t['merchant_id']
            if mid not in seen:
                seen.add(mid)
                all_predictions.append(t)

    # Sort soonest first (overdue = negative days_until appear at top)
    all_predictions.sort(key=lambda t: t['days_until'])

    W_MID, W_DATE = 36, 12
    print(f'\n{"=" * 92}')
    print(f'  RENEWAL DASHBOARD  (reference: {REFERENCE_DATE})')
    print(f'{"=" * 92}')
    print(f'  {"Merchant":<{W_MID}}  {"Last Charge":<{W_DATE}}  '
          f'{"Next Charge":<{W_DATE}}  {"Days":>6}  {"Conf":<8}  {"±Band":>6}')
    print(f'  {"-"*W_MID}  {"-"*W_DATE}  {"-"*W_DATE}  {"-"*6}  {"-"*8}  {"-"*6}')
    for t in all_predictions:
        band_str = f'±{t["confidence_band_days"]}d' if t['confidence_band_days'] else '—'
        overdue  = '  [OVERDUE]' if t['days_until'] < 0 else ''
        print(f'  {t["merchant_id"]:<{W_MID}}  {t["last_charge_date"]:<{W_DATE}}  '
              f'{t["next_charge_date"]:<{W_DATE}}  {t["days_until"]:>6}  '
              f'{t["confidence"]:<8}  {band_str:>6}{overdue}')
    print(f'{"=" * 92}')
    print(f'  {len(all_predictions)} merchants total  |  '
          f'{sum(1 for t in all_predictions if t["confidence"] == "high")} high-confidence  |  '
          f'{sum(1 for t in all_predictions if t["is_cold_start"])} cold-start')
