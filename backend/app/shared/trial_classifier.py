"""
Free-trial classifier for grouped merchant charge histories.
Detects merchants whose charge history looks like a free/discounted trial
converting to full price.

SubscriptionSense groups recurring merchant transactions before calling this
module. The classifier combines interval features, price-step changes, and a
cold-start prior to estimate whether a merchant is converting from trial or
discounted pricing to full-price billing.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

# Constants

#: Common trial-period lengths in days
TRIAL_PERIODS = [7, 14, 30, 365]

#: A charge interval counts as matching a trial period if it is within
#: this many days of a canonical trial length.
TRIAL_PERIOD_TOLERANCE = 3

#: Ordered feature names - defines the column layout of the feature matrix.
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


# Feature extraction

def extract_trial_features(transactions: list[dict]) -> dict:
    """Compute the trial-detection feature vector for a single merchant's charge history. The returned dictionary has the keys listed in ``FEATURE_KEYS`` and combines interval statistics, the first-charge ratio, a trial-period match flag, a price-step-up indicator, and a cold-start indicator."""
    if not transactions:
        return {k: 0 for k in FEATURE_KEYS}

    sorted_txns = sorted(transactions, key=lambda t: t['date'])
    amounts = [abs(t['amount']) for t in sorted_txns]

    n = len(amounts)
    first = amounts[0]
    med = float(np.median(amounts))

    # Avoid division by zero - if median is 0 (e.g. all zero charges), ratio = 1.0
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


# Synthetic training data

def _make_synthetic_txns(amounts: list[float],
                         intervals: list[int],
                         start: str = '2025-01-01') -> list[dict]:
    """Construct a minimal transaction list from a sequence of amounts and inter-charge intervals for the synthetic training dataset."""
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
    """Build a labelled feature matrix and label vector from canonical trial and non-trial charge patterns. The label is ``1`` for trial-style patterns and ``0`` otherwise."""
    # Each scenario is a tuple of ``(amounts, intervals, label)``.
    scenarios: list[tuple[list[float], list[int], int]] = [
        # Netflix: $0 trial -> ~$1499/month at 30-day intervals
        ([0.01, 1499, 1499, 1499],           [30, 30, 30],       1),
        # Spotify: 3-month discounted -> full price
        ([99, 99, 99, 999, 999, 999],        [30, 30, 30, 30, 30], 1),
        # Adobe: 7-day -> monthly full price
        ([1, 3500, 3500, 3500],              [7, 30, 30],         1),
        # Google One: 14-day -> monthly
        ([50, 500, 500, 500],                [14, 30, 30],        1),
        # Canva Pro: 30-day -> monthly
        ([0.01, 1800, 1800, 1800],           [30, 30, 30],        1),
        # Hulu: 7-day -> monthly
        ([0.01, 800, 800],                   [7, 30],             1),
        # Apple One: 7-day -> monthly
        ([0.01, 2500, 2500, 2500, 2500],     [7, 30, 30, 30],     1),
        # Annual plan: 14-day trial -> yearly billing
        ([0.01, 15000, 15000],               [14, 365],           1),
        # Dropbox: discounted first month -> full price
        ([100, 1200, 1200, 1200],            [30, 30, 30],        1),
        # Generic: low first -> full price at 30 days
        ([200, 1800, 1800],                  [30, 30],            1),
        # Generic: 14-day trial
        ([1, 5000, 5000, 5000],              [14, 30, 30],        1),
        # Gym: introductory first month
        ([100, 2500, 2500, 2500],            [30, 30, 30],        1),
        # Cold-start trial - 2 charges, big jump
        ([50, 999],                          [30],                1),
        ([0.01, 1500],                       [14],                1),
        # 7-day trial -> extended monthly
        ([0.01, 999, 999, 999, 999],         [7, 30, 30, 30],     1),

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
        # Annual subscription - same price both years (no step-up)
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


# Model training

def train_classifier(X: np.ndarray, y: np.ndarray) -> Pipeline:
    """Train a logistic-regression classifier on the supplied feature matrix and labels. The pipeline applies ``StandardScaler`` so monetary amounts and boolean flags share a common scale, and ``class_weight='balanced'`` compensates for the low frequency of trial cases in typical statement data. The returned pipeline exposes ``predict_proba`` like a bare classifier."""
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


# Prediction

def predict_trial_intent(merchant_transactions: list[dict],
                         model: Pipeline) -> float:
    """Return the probability of trial intent for a single merchant's charge history. When fewer than three charges are available, the raw model score is blended with a Bayesian cold-start prior; otherwise the model score is returned directly."""
    features   = extract_trial_features(merchant_transactions)
    vec        = _features_to_vector(features).reshape(1, -1)
    model_score = float(model.predict_proba(vec)[0][1])

    if features['is_cold_start']:
        pw, mw = COLD_START_WEIGHTS
        return pw * COLD_START_PRIOR + mw * model_score

    return model_score


# Batch classification

def classify_all_merchants(transactions: list[dict],
                           model: Pipeline,
                           threshold: float = 0.60) -> list[dict]:
    """Annotate every transaction with ``trial_score`` and ``trial_flag``. Transactions are grouped by ``merchant_id``, scored once per group, and the score is propagated to every row in the group. The input list is not mutated; a new annotated list is returned."""
    if not transactions:
        return []

    result = [dict(t) for t in transactions]

    groups: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(result):
        groups[t['merchant_id']].append(i)

    for mid, indices in groups.items():
        group_txns = [result[i] for i in indices]
        score = predict_trial_intent(group_txns, model)
        for i in indices:
            result[i]['trial_score'] = round(score, 4)
            result[i]['trial_flag']  = bool(score > threshold)

    return result

