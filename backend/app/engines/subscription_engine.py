"""
SubscriptionSense Engine — Detects, classifies, and predicts subscriptions.

Integrates three team members' work:
  1. capstone_revised   — Universal PDF extraction (pdfplumber + camelot + Gemini)
  2. subscription_detection_alg — Subscription detection (statistical period analysis)
  3. Capstone.trial_classifier  — Free trial detection (sklearn LogisticRegression)
  4. Capstone.currency_normaliser — JMD → USD conversion (BOJ rates)

No code is copied from RenewalSense — each module is imported from its source.
"""

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, stdev

logger = logging.getLogger(__name__)

# ── External module imports ──────────────────────────────────────────

# 1. Universal PDF extraction
from capstone_revised.extract_transactions import extract_from_bytes

# 2. Classmate's subscription detection algorithm
from subscription_detection_alg import (
    Transaction as DetectionTransaction,
    detect_subscriptions as _detect_subs,
)

# 3. Free trial classifier (Capstone — sklearn-based)
from Capstone.Capstone.trial_classifier import (
    build_synthetic_dataset,
    train_classifier,
    extract_trial_features,
    predict_trial_intent,
)

# 4. Currency normaliser (Capstone — JMD → USD)
from Capstone.Capstone.currency_normaliser import (
    normalise_amount,
    get_rate_with_fallback,
    FALLBACK_RATE,
)

# ── Train trial classifier once at module load ───────────────────────
_X, _y = build_synthetic_dataset()
_trial_model = train_classifier(_X, _y)
logger.info(f"Trial classifier trained on {len(_y)} synthetic samples "
            f"({_y.sum()} trial, {(_y == 0).sum()} non-trial)")


# =====================================================================
# CUSUM Price Change Detection (standalone implementation)
# =====================================================================

def _detect_price_changes(transactions: list[dict]) -> list[dict]:
    """
    Detect structural price changes in recurring merchant charges
    using Cumulative Sum (CUSUM) analysis.

    Groups transactions by vendor, computes running CUSUM on the
    charge amounts, and flags significant deviations.
    """
    # Group debits by vendor
    vendor_charges: dict[str, list[dict]] = defaultdict(list)
    for tx in transactions:
        if tx.get("debit", 0) > 0:
            vendor = tx.get("vendor_name") or tx.get("description", "")
            vendor_charges[vendor.strip().lower()].append(tx)

    changes = []

    for vendor, charges in vendor_charges.items():
        if len(charges) < 3:
            continue

        # Sort chronologically
        sorted_charges = sorted(charges, key=lambda t: t["date"])
        amounts = [c["debit"] for c in sorted_charges]

        # Compute baseline (mean of first half)
        half = max(2, len(amounts) // 2)
        baseline = mean(amounts[:half])

        if baseline == 0:
            continue

        # CUSUM: cumulative deviation from baseline
        cusum_pos = 0.0
        cusum_neg = 0.0
        threshold = baseline * 0.20  # 20% deviation triggers alert

        for i in range(half, len(amounts)):
            deviation = amounts[i] - baseline
            cusum_pos = max(0, cusum_pos + deviation)
            cusum_neg = min(0, cusum_neg + deviation)

            if cusum_pos > threshold:
                # Price increase detected
                new_avg = mean(amounts[i:]) if i < len(amounts) else amounts[i]
                change_pct = ((new_avg - baseline) / baseline) * 100

                display_name = sorted_charges[0].get("vendor_name") or vendor.title()
                date_str = sorted_charges[i]["date"]
                if isinstance(date_str, datetime):
                    date_str = date_str.strftime("%Y-%m-%d")

                changes.append({
                    "subscription": display_name,
                    "type": "price_increase",
                    "severity": "warning",
                    "date": date_str,
                    "old_amount": round(baseline, 2),
                    "new_amount": round(new_avg, 2),
                    "change_amount": round(new_avg - baseline, 2),
                    "change_percent": round(change_pct, 1),
                    "description": f"{display_name} charge increased from "
                                   f"${baseline:,.2f} to ${new_avg:,.2f} "
                                   f"({change_pct:+.1f}%)",
                })
                break  # One alert per vendor

            if cusum_neg < -threshold:
                # Price decrease detected
                new_avg = mean(amounts[i:]) if i < len(amounts) else amounts[i]
                change_pct = ((new_avg - baseline) / baseline) * 100

                display_name = sorted_charges[0].get("vendor_name") or vendor.title()
                date_str = sorted_charges[i]["date"]
                if isinstance(date_str, datetime):
                    date_str = date_str.strftime("%Y-%m-%d")

                changes.append({
                    "subscription": display_name,
                    "type": "price_decrease",
                    "severity": "info",
                    "date": date_str,
                    "old_amount": round(baseline, 2),
                    "new_amount": round(new_avg, 2),
                    "change_amount": round(new_avg - baseline, 2),
                    "change_percent": round(change_pct, 1),
                    "description": f"{display_name} charge decreased from "
                                   f"${baseline:,.2f} to ${new_avg:,.2f} "
                                   f"({change_pct:+.1f}%)",
                })
                break

    return changes


# =====================================================================
# Transaction classification (lightweight keyword-based)
# =====================================================================

_SUBSCRIPTION_KEYWORDS = {
    'netflix': 'Netflix', 'spotify': 'Spotify', 'youtube': 'YouTube',
    'disney': 'Disney+', 'hulu': 'Hulu', 'hbo': 'HBO Max',
    'apple music': 'Apple Music', 'apple tv': 'Apple TV+',
    'amazon prime': 'Amazon Prime', 'audible': 'Audible',
    'tidal': 'Tidal', 'icloud': 'iCloud', 'google one': 'Google One',
    'dropbox': 'Dropbox', 'microsoft 365': 'Microsoft 365',
    'adobe': 'Adobe', 'canva': 'Canva', 'chatgpt': 'ChatGPT',
    'openai': 'OpenAI', 'notion': 'Notion', 'grammarly': 'Grammarly',
    'duolingo': 'Duolingo', 'headspace': 'Headspace',
    'flow': 'Flow', 'digicel': 'Digicel',
    'playstation': 'PlayStation', 'xbox': 'Xbox',
    'nintendo': 'Nintendo', 'steam': 'Steam',
}


def _classify_transactions(transactions: list[dict]) -> list[dict]:
    """Add category and vendor_name fields to transactions."""
    for tx in transactions:
        desc_lower = (tx.get("description") or "").lower()
        vendor_name = tx.get("description", "")
        category = "other"

        for keyword, name in _SUBSCRIPTION_KEYWORDS.items():
            if keyword in desc_lower:
                category = "subscription"
                vendor_name = name
                break

        tx["category"] = category
        tx["vendor_name"] = vendor_name

    return transactions


# =====================================================================
# Format converter (capstone_revised → engine format)
# =====================================================================

def _convert_to_engine_format(universal_txs: list[dict]) -> list[dict]:
    """Convert capstone_revised output to engine dict format."""
    converted = []
    for tx in universal_txs:
        date_val = tx.get("date")
        if isinstance(date_val, str):
            try:
                date_val = datetime.strptime(date_val, "%Y-%m-%d")
            except ValueError:
                continue
        elif not isinstance(date_val, datetime):
            continue

        amount = tx.get("amount", 0) or 0
        debit = abs(amount) if amount < 0 else 0
        credit = amount if amount > 0 else 0

        converted.append({
            "date": date_val,
            "description": tx.get("description", ""),
            "debit": debit,
            "credit": credit,
            "balance": tx.get("balance") or 0,
            "currency": tx.get("currency", "JMD"),
            "amount": amount,  # Keep signed amount for trial classifier
        })

    return converted


# =====================================================================
# Subscription detection (classmate's algorithm)
# =====================================================================

def _run_subscription_detection(classified_txs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Convert engine transactions → classmate's Transaction objects,
    run detect_subscriptions(), return (subscriptions, renewal_predictions).
    """
    # Build Detection Transactions from debits
    detection_txs = []
    for tx in classified_txs:
        if tx["debit"] > 0:
            detection_txs.append(DetectionTransaction(
                date=tx["date"],
                amount=tx["debit"],
                merchant=tx.get("vendor_name") or tx["description"],
            ))

    if not detection_txs:
        return [], []

    detected_subs = _detect_subs(detection_txs, min_occurrences=2)

    subscriptions = []
    renewal_predictions = []
    today = datetime.now()

    for sub in detected_subs:
        # Determine typical renewal day-of-month
        days = [t.date.day if hasattr(t.date, "day") else t.date
                for t in sub.transactions]
        renewal_day = max(set(days), key=days.count) if days else 1

        subscriptions.append({
            "merchant": sub.merchant,
            "amount": round(sub.avg_amount, 2),
            "period": sub.period or "unknown",
            "period_days": sub.period_days,
            "confidence": sub.confidence,
            "charge_count": len(sub.transactions),
            "renewal_day": renewal_day,
            "last_charge": max(t.date for t in sub.transactions).strftime("%Y-%m-%d"),
        })

        # Renewal prediction
        next_due = sub.next_expected()
        if next_due is not None:
            if isinstance(next_due, datetime):
                next_date = next_due
            else:
                next_date = datetime.combine(next_due, datetime.min.time())

            while next_date < today:
                next_date += timedelta(days=int(sub.period_days or 30))

            days_until = (next_date - today).days

            if sub.confidence >= 0.8:
                conf_label = "high"
            elif sub.confidence >= 0.5:
                conf_label = "medium"
            else:
                conf_label = "low"

            band = max(2, round((1 - sub.confidence) * 10))

            renewal_predictions.append({
                "subscription": sub.merchant,
                "next_charge_date": next_date.strftime("%Y-%m-%d"),
                "days_until_charge": days_until,
                "period": sub.period,
                "period_days": sub.period_days,
                "confidence": sub.confidence,
                "confidence_label": conf_label,
                "confidence_window": {
                    "earliest": (next_date - timedelta(days=band)).strftime("%Y-%m-%d"),
                    "latest": (next_date + timedelta(days=band)).strftime("%Y-%m-%d"),
                    "band_days": band,
                },
                "data_points": len(sub.transactions),
                "last_charge_date": max(t.date for t in sub.transactions).strftime("%Y-%m-%d"),
            })

    renewal_predictions.sort(key=lambda p: p["days_until_charge"])

    return subscriptions, renewal_predictions


# =====================================================================
# Free trial detection (Capstone trial_classifier)
# =====================================================================

def _detect_trials(classified_txs: list[dict]) -> list[dict]:
    """
    Group transactions by vendor, run trial classifier on each group.
    Returns list of merchants flagged as likely free trial → paid conversions.
    """
    # Group by vendor
    vendor_groups: dict[str, list[dict]] = defaultdict(list)
    for tx in classified_txs:
        if tx["debit"] > 0:
            vendor = (tx.get("vendor_name") or tx["description"]).strip()
            vendor_groups[vendor].append({
                "date": tx["date"].strftime("%Y-%m-%d") if isinstance(tx["date"], datetime) else str(tx["date"]),
                "amount": -tx["debit"],  # trial classifier expects negative amounts for debits
                "merchant_id": vendor,
            })

    trial_alerts = []

    for vendor, txns in vendor_groups.items():
        if len(txns) < 2:
            continue

        score = predict_trial_intent(txns, _trial_model)

        if score >= 0.55:  # Flag as potential trial
            amounts = [abs(t["amount"]) for t in sorted(txns, key=lambda t: t["date"])]
            first_charge = amounts[0]
            latest_charge = amounts[-1]

            if first_charge < latest_charge:
                change_type = "trial_to_paid"
                desc = (f"First charge was ${first_charge:,.2f}, "
                        f"now ${latest_charge:,.2f} — possible trial conversion")
            else:
                change_type = "promotional"
                desc = (f"Charge pattern suggests an introductory offer "
                        f"(${first_charge:,.2f} → ${latest_charge:,.2f})")

            trial_alerts.append({
                "merchant": vendor,
                "trial_score": round(score, 3),
                "type": change_type,
                "first_charge": round(first_charge, 2),
                "current_charge": round(latest_charge, 2),
                "charge_count": len(txns),
                "description": desc,
            })

    # Sort by score descending
    trial_alerts.sort(key=lambda a: a["trial_score"], reverse=True)
    return trial_alerts


# =====================================================================
# Currency normalization
# =====================================================================

def _normalize_currency(classified_txs: list[dict]) -> dict:
    """
    Compute USD equivalents for all transactions.
    Returns a summary dict with exchange rate and totals.
    """
    rate_cache: dict[str, float] = {}
    total_debits_jmd = 0.0
    total_credits_jmd = 0.0

    for tx in classified_txs:
        total_debits_jmd += tx.get("debit", 0)
        total_credits_jmd += tx.get("credit", 0)

    # Get rate for the most recent transaction
    if classified_txs:
        sorted_txs = sorted(classified_txs, key=lambda t: t["date"], reverse=True)
        latest_date = sorted_txs[0]["date"]
        date_str = latest_date.strftime("%Y-%m-%d") if isinstance(latest_date, datetime) else str(latest_date)
        rate = get_rate_with_fallback(date_str, rate_cache)
    else:
        rate = FALLBACK_RATE

    currency = classified_txs[0].get("currency", "JMD") if classified_txs else "JMD"

    if currency.upper() == "USD":
        return {
            "original_currency": "USD",
            "exchange_rate": 1.0,
            "total_debits_local": round(total_debits_jmd, 2),
            "total_credits_local": round(total_credits_jmd, 2),
            "total_debits_usd": round(total_debits_jmd, 2),
            "total_credits_usd": round(total_credits_jmd, 2),
        }

    return {
        "original_currency": currency.upper(),
        "exchange_rate": round(rate, 2),
        "total_debits_local": round(total_debits_jmd, 2),
        "total_credits_local": round(total_credits_jmd, 2),
        "total_debits_usd": round(normalise_amount(total_debits_jmd, rate), 2),
        "total_credits_usd": round(normalise_amount(total_credits_jmd, rate), 2),
    }


# =====================================================================
# MAIN ENTRY POINT
# =====================================================================

def analyze_subscriptions(file_bytes: bytes) -> dict:
    """
    Main entry point: takes PDF bytes, returns full subscription analysis.

    Pipeline:
      1. Extract transactions (capstone_revised — any bank)
      2. Classify transactions (keyword matching)
      3. Detect subscriptions (classmate's statistical algorithm)
      4. Detect free trials (Capstone sklearn classifier)
      5. Detect price changes (CUSUM)
      6. Normalize currency (JMD → USD)
    """
    # 1. Extract
    logger.info("Step 1: Extracting transactions...")
    raw_transactions = extract_from_bytes(file_bytes)
    if not raw_transactions:
        return {"error": "No transactions found in the PDF. Check the statement format."}

    # Detect bank/currency from raw output
    bank_detected = raw_transactions[0].get("bank", "Unknown") if raw_transactions else "Unknown"
    currency_detected = raw_transactions[0].get("currency", "JMD") if raw_transactions else "JMD"

    # Convert format
    transactions = _convert_to_engine_format(raw_transactions)
    if not transactions:
        return {"error": "Could not parse any valid transactions from the PDF."}

    logger.info(f"Step 1 complete: {len(transactions)} transactions from {bank_detected}")

    # 2. Classify
    logger.info("Step 2: Classifying transactions...")
    classified = _classify_transactions(transactions)

    categories: dict[str, int] = {}
    for tx in classified:
        cat = tx.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1

    # 3. Detect subscriptions
    logger.info("Step 3: Detecting subscriptions...")
    subscriptions, renewal_predictions = _run_subscription_detection(classified)
    logger.info(f"Step 3 complete: {len(subscriptions)} subscription(s), "
                f"{len(renewal_predictions)} prediction(s)")

    # 4. Detect free trials
    logger.info("Step 4: Detecting free trials...")
    trial_alerts = _detect_trials(classified)
    logger.info(f"Step 4 complete: {len(trial_alerts)} trial alert(s)")

    # 5. Detect price changes
    logger.info("Step 5: Detecting price changes...")
    price_changes = _detect_price_changes(classified)
    logger.info(f"Step 5 complete: {len(price_changes)} price change(s)")

    # 6. Currency normalization
    logger.info("Step 6: Normalizing currency...")
    currency_summary = _normalize_currency(classified)
    logger.info(f"Step 6 complete: {currency_summary['original_currency']} → USD "
                f"@ {currency_summary['exchange_rate']}")

    # Build transaction list for display
    tx_list = []
    for tx in classified:
        tx_list.append({
            "date": tx["date"].strftime("%Y-%m-%d") if isinstance(tx["date"], datetime) else str(tx["date"]),
            "description": tx["description"],
            "debit": tx["debit"],
            "credit": tx["credit"],
            "category": tx.get("category", "other"),
            "vendor_name": tx.get("vendor_name", ""),
        })

    total_sub_cost = sum(s["amount"] for s in subscriptions)

    return {
        "transactions_parsed": len(transactions),
        "bank_detected": bank_detected,
        "currency": currency_detected,
        "categories": categories,
        "transactions": tx_list,
        "subscriptions": subscriptions,
        "renewal_predictions": renewal_predictions,
        "trial_alerts": trial_alerts,
        "price_changes": price_changes,
        "currency_summary": currency_summary,
        "summary": {
            "total_subscriptions": len(subscriptions),
            "total_sub_cost": round(total_sub_cost, 2),
            "total_trial_alerts": len(trial_alerts),
            "total_price_changes": len(price_changes),
            "total_debits": round(sum(tx["debit"] for tx in classified), 2),
            "total_credits": round(sum(tx["credit"] for tx in classified), 2),
        },
    }
