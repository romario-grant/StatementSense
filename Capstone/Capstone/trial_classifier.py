"""
Statement Sense — Free-Trial Classifier  (Feature 7.3)
Detects merchants whose charge history looks like a free/discounted trial
converting to full price.

Pipeline position:
    pdf_parsers → transaction_filter → merchant_normaliser
                                               ↓
                                     trial_classifier  ← here
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

#: Common trial-period lengths in days
TRIAL_PERIODS = [7, 14, 30, 365]

#: A charge interval counts as matching a trial period if it is within
#: this many days of a canonical trial length.
TRIAL_PERIOD_TOLERANCE = 3

#: Ordered feature names — defines the column layout of the feature matrix.
FEATURE_KEYS = [
    'n_charges',
    'first_charge',
    'median_charge',
    'first_ratio',
    'min_interval_days',
    'max_interval_days',
    'matches_trial_period',
    'has_price_stepup',
    'is_cold_start',
]

#: Bayesian prior probability of trial intent applied to cold-start merchants
COLD_START_PRIOR = 0.3

#: Blend weights for cold-start scoring: (prior_weight, model_weight)
COLD_START_WEIGHTS = (0.4, 0.6)


# ─────────────────────────────────────────────
# Feature extraction
# ─────────────────────────────────────────────

def extract_trial_features(transactions: list[dict]) -> dict:
    """
    Compute trial-detection features for all charges to **one** merchant_id.

    Parameters
    ----------
    transactions : list of transaction dicts (already filtered to one merchant)

    Returns
    -------
    dict with keys matching FEATURE_KEYS:
    - n_charges            — number of charges
    - first_charge         — absolute amount of the first (chronological) charge
    - median_charge        — median absolute amount across all charges
    - first_ratio          — first_charge / median_charge  (low → possible trial)
    - min_interval_days    — shortest gap between consecutive charges
    - max_interval_days    — longest  gap between consecutive charges
    - matches_trial_period — 1 if any interval is within TRIAL_PERIOD_TOLERANCE
                             days of 7, 14, 30 or 365; else 0
    - has_price_stepup     — 1 if any charge exceeds 1.5× the first charge
    - is_cold_start        — 1 if n_charges < 3
    """
    if not transactions:
        return {k: 0 for k in FEATURE_KEYS}

    # Sort chronologically
    sorted_txns = sorted(transactions, key=lambda t: t['date'])
    amounts = [abs(t['amount']) for t in sorted_txns]

    n = len(amounts)
    first = amounts[0]
    med = float(np.median(amounts))

    # Avoid division by zero — if median is 0 (e.g. all zero charges), ratio = 1.0
    first_ratio = (first / med) if med > 0 else 1.0

    # Inter-charge intervals
    dates = [datetime.strptime(t['date'], '%Y-%m-%d').date()
             for t in sorted_txns]
    intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]

    min_interval = min(intervals) if intervals else 0
    max_interval = max(intervals) if intervals else 0

    matches_trial = int(
        any(
            abs(iv - tp) <= TRIAL_PERIOD_TOLERANCE
            for iv in intervals
            for tp in TRIAL_PERIODS
        )
        if intervals else False
    )

    has_stepup = int(
        any(a > 1.5 * first for a in amounts[1:])
        if n > 1 else False
    )

    return {
        'n_charges':           n,
        'first_charge':        first,
        'median_charge':       med,
        'first_ratio':         first_ratio,
        'min_interval_days':   min_interval,
        'max_interval_days':   max_interval,
        'matches_trial_period': matches_trial,
        'has_price_stepup':    has_stepup,
        'is_cold_start':       int(n < 3),
    }


def _features_to_vector(features: dict) -> np.ndarray:
    """Serialise a feature dict into a 1-D numpy array (FEATURE_KEYS order)."""
    return np.array([features[k] for k in FEATURE_KEYS], dtype=float)


# ─────────────────────────────────────────────
# Synthetic training data
# ─────────────────────────────────────────────

def _make_synthetic_txns(amounts: list[float],
                         intervals: list[int],
                         start: str = '2025-01-01') -> list[dict]:
    """
    Build a minimal transaction list from amounts + day-gaps.
    Used only for constructing the synthetic training set.
    """
    from datetime import date, timedelta
    d = date.fromisoformat(start)
    txns = []
    for i, amt in enumerate(amounts):
        txns.append({'date': d.isoformat(), 'amount': -abs(amt),
                     'merchant_id': 'SYN'})
        if i < len(intervals):
            d += timedelta(days=intervals[i])
    return txns


def build_synthetic_dataset() -> tuple[np.ndarray, np.ndarray]:
    """
    Build a labelled feature matrix from known trial / non-trial patterns.

    Returns
    -------
    X : ndarray, shape (n_samples, n_features)
    y : ndarray, shape (n_samples,)  — 1 = trial, 0 = non-trial
    """
    # (amounts_list, intervals_list, label)
    scenarios: list[tuple[list[float], list[int], int]] = [
        # ── TRIALS (label = 1) ─────────────────────────────────────
        # Netflix: $0 trial → ~$1499/month at 30-day intervals
        ([0.01, 1499, 1499, 1499],           [30, 30, 30],       1),
        # Spotify: 3-month discounted → full price
        ([99, 99, 99, 999, 999, 999],        [30, 30, 30, 30, 30], 1),
        # Adobe: 7-day → monthly full price
        ([1, 3500, 3500, 3500],              [7, 30, 30],         1),
        # Google One: 14-day → monthly
        ([50, 500, 500, 500],                [14, 30, 30],        1),
        # Canva Pro: 30-day → monthly
        ([0.01, 1800, 1800, 1800],           [30, 30, 30],        1),
        # Hulu: 7-day → monthly
        ([0.01, 800, 800],                   [7, 30],             1),
        # Apple One: 7-day → monthly
        ([0.01, 2500, 2500, 2500, 2500],     [7, 30, 30, 30],     1),
        # Annual plan: 14-day trial → yearly billing
        ([0.01, 15000, 15000],               [14, 365],           1),
        # Dropbox: discounted first month → full price
        ([100, 1200, 1200, 1200],            [30, 30, 30],        1),
        # Generic: low first → full price at 30 days
        ([200, 1800, 1800],                  [30, 30],            1),
        # Generic: 14-day trial
        ([1, 5000, 5000, 5000],              [14, 30, 30],        1),
        # Gym: introductory first month
        ([100, 2500, 2500, 2500],            [30, 30, 30],        1),
        # Cold-start trial — 2 charges, big jump
        ([50, 999],                          [30],                1),
        ([0.01, 1500],                       [14],                1),
        # 7-day trial → extended monthly
        ([0.01, 999, 999, 999, 999],         [7, 30, 30, 30],     1),

        # ── NON-TRIALS (label = 0) ─────────────────────────────────
        # HI-LO grocery: variable weekly
        ([2500, 3200, 2800, 3100, 2700],     [7, 7, 7, 7],        0),
        # KFC: variable monthly
        ([3000, 3200, 2900, 3100],           [28, 32, 29],        0),
        # Established Netflix (past trial): stable monthly
        ([1499, 1499, 1499, 1499, 1499],     [30, 30, 30, 30],    0),
        # Utility bill: variable monthly
        ([12000, 12500, 11800, 13000, 12200], [30, 30, 30, 30],   0),
        # Established Spotify: stable monthly
        ([999, 999, 999, 999],               [30, 30, 30],        0),
        # Grocery: irregular spend
        ([1800, 2200, 1500, 2600, 1900, 2100], [6, 8, 5, 7, 9],  0),
        # Coffee shop: small irregular
        ([450, 600, 350, 500, 450],          [3, 5, 7, 2],        0),
        # Internet bill: stable monthly
        ([3500, 3500, 3500, 3500, 3500],     [30, 30, 30, 30],    0),
        # Phone bill: near-stable monthly
        ([5000, 5100, 4900, 5050],           [30, 30, 30],        0),
        # Cold-start one-off purchase
        ([8000],                             [],                  0),
        ([1500],                             [],                  0),
        # Two stable charges (not a step-up)
        ([2500, 2700],                       [15],                0),
        ([3000, 2900],                       [30],                0),
        # Annual subscription — same price both years (no step-up)
        ([15000, 15000, 15000],              [365, 365],          0),
        # Digicel top-up: variable, irregular short gaps
        ([1000, 2000, 1500, 3000, 1000],     [5, 3, 10, 7],       0),
        # Large bank transfer: stable monthly
        ([50000, 50000, 50000],              [30, 30],            0),
        # Transport: small weekly variable
        ([1000, 1100, 900, 1050, 950],       [7, 7, 7, 7],        0),
        # Restaurant: irregular meals
        ([3000, 4500, 2800, 5000, 3200],     [14, 7, 21, 10],     0),
        # ABM withdrawal: large irregular
        ([20000, 35000, 15000, 40000],       [10, 14, 20],        0),
        # Pharmacy: irregular
        ([600, 1200, 800, 1500],             [14, 30, 7],         0),
    ]

    rows, labels = [], []
    for amounts, intervals, label in scenarios:
        txns = _make_synthetic_txns(amounts, intervals)
        feats = extract_trial_features(txns)
        rows.append(_features_to_vector(feats))
        labels.append(label)

    return np.array(rows), np.array(labels)


# ─────────────────────────────────────────────
# Model training
# ─────────────────────────────────────────────

def train_classifier(X: np.ndarray, y: np.ndarray) -> Pipeline:
    """
    Train a LogisticRegression classifier on the labelled feature matrix.

    Uses StandardScaler (feature magnitudes vary wildly — JMD amounts vs 0/1 flags)
    and class_weight='balanced' because trials are uncommon in typical statement data.

    Returns a fitted sklearn Pipeline (scaler + classifier) that exposes
    ``predict_proba`` just like a bare LogisticRegression.
    """
    pipe = Pipeline([
        ('scaler', StandardScaler()),
        ('clf',    LogisticRegression(
            max_iter=2000,
            class_weight='balanced',
            solver='lbfgs',
        )),
    ])
    pipe.fit(X, y)
    return pipe


# ─────────────────────────────────────────────
# Prediction
# ─────────────────────────────────────────────

def predict_trial_intent(merchant_transactions: list[dict],
                         model: Pipeline) -> float:
    """
    Return P(trial_intent) ∈ [0, 1] for a single merchant's transaction group.

    Cold-start blending
    -------------------
    When n_charges < 3 the model has little signal.  We blend the model score
    with a Bayesian prior to avoid extreme predictions:

        score = 0.4 × COLD_START_PRIOR + 0.6 × model_score
              = 0.12 + 0.6 × model_score  →  always in [0.12, 0.72]

    When n_charges ≥ 3, score = model_score directly.
    """
    features   = extract_trial_features(merchant_transactions)
    vec        = _features_to_vector(features).reshape(1, -1)
    model_score = float(model.predict_proba(vec)[0][1])

    if features['is_cold_start']:
        pw, mw = COLD_START_WEIGHTS
        return pw * COLD_START_PRIOR + mw * model_score

    return model_score


# ─────────────────────────────────────────────
# Batch classification
# ─────────────────────────────────────────────

def classify_all_merchants(transactions: list[dict],
                           model: Pipeline,
                           threshold: float = 0.60) -> list[dict]:
    """
    Stamp ``trial_score`` and ``trial_flag`` onto every transaction dict.

    Groups transactions by ``merchant_id``, calls ``predict_trial_intent``
    once per group, then fans the result back out to every row in that group.

    Parameters
    ----------
    transactions : filtered + normalised transaction list
                   (each dict must have a ``merchant_id`` key)
    model        : fitted Pipeline from ``train_classifier``
    threshold    : P(trial) threshold for setting trial_flag = True

    Returns a new list of dicts; the input is not mutated.
    """
    if not transactions:
        return []

    result = [dict(t) for t in transactions]

    # Group indices by merchant_id
    groups: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(result):
        groups[t['merchant_id']].append(i)

    # Score each group once, fan results back to rows
    for mid, indices in groups.items():
        group_txns = [result[i] for i in indices]
        score = predict_trial_intent(group_txns, model)
        for i in indices:
            result[i]['trial_score'] = round(score, 4)
            result[i]['trial_flag']  = bool(score > threshold)

    return result


# ─────────────────────────────────────────────
# Smoke test
# ─────────────────────────────────────────────

if __name__ == '__main__':
    from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
    from transaction_filter import filter_transactions
    from merchant_normaliser import cluster_merchants

    NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
    SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
                   r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')

    # Train once
    X, y = build_synthetic_dataset()
    model = train_classifier(X, y)
    print(f'Model trained on {len(y)} synthetic samples '
          f'({y.sum()} trial, {(y == 0).sum()} non-trial)\n')

    for bank, path, parser in [
        ('NCB',        NCB_PATH,    parse_ncb_pdf),
        ('Scotiabank', SCOTIA_PATH, parse_scotiabank_pdf),
    ]:
        raw       = parser(path)
        filtered  = filter_transactions(raw)
        clustered = cluster_merchants(filtered)
        scored    = classify_all_merchants(clustered, model)

        # Deduplicate — one row per merchant_id for display
        seen: set[str] = set()
        merchant_rows: list[dict] = []
        for t in scored:
            mid = t['merchant_id']
            if mid not in seen:
                seen.add(mid)
                merchant_rows.append(t)
        merchant_rows.sort(key=lambda t: t['trial_score'], reverse=True)

        flagged = sum(1 for t in merchant_rows if t['trial_flag'])
        print(f'{"=" * 65}')
        print(f'  {bank}  |  {len(merchant_rows)} merchants  |  '
              f'{flagged} flagged as trial')
        print(f'{"=" * 65}')
        for t in merchant_rows:
            flag = '[TRIAL]' if t['trial_flag'] else '       '
            print(f'  {flag}  {t["trial_score"]:.3f}  {t["merchant_id"]}')
        print()
