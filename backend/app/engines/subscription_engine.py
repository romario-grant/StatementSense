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
import re
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, median

logger = logging.getLogger(__name__)

# ── External module imports ──────────────────────────────────────────

# 1. Universal PDF extraction
from capstone_revised.extract_transactions import extract_from_bytes

# 2. Classmate's subscription detection algorithm
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

def _detect_price_changes(transactions: list[dict], confirmed_merchants: set[str] | None = None) -> list[dict]:
    """
    Detect structural price changes in recurring merchant charges
    using Cumulative Sum (CUSUM) analysis.

    Groups transactions by vendor, computes running CUSUM on the
    charge amounts, and flags significant deviations.
    """
    # Group eligible recurring merchant debits by vendor.
    vendor_charges: dict[str, list[dict]] = defaultdict(list)
    for tx in transactions:
        if _is_subscription_candidate(tx) and not _is_variable_spend(tx):
            vendor = tx.get("vendor_name") or tx.get("description", "")
            if confirmed_merchants is not None and vendor not in confirmed_merchants:
                continue
            vendor_charges[vendor.strip().lower()].append(tx)

    changes = []

    for vendor, charges in vendor_charges.items():
        if len(charges) < 3:
            continue

        # Sort chronologically
        sorted_charges = sorted(charges, key=lambda t: t["date"])
        if len({c["date"].date() if isinstance(c["date"], datetime) else c["date"] for c in sorted_charges}) < 3:
            continue
        amounts = [c["debit"] for c in sorted_charges]

        # Compute baseline (mean of first half)
        half = max(2, len(amounts) // 2)
        baseline = mean(amounts[:half])

        if baseline == 0:
            continue

        # CUSUM: cumulative deviation from baseline
        cusum_pos = 0.0
        cusum_neg = 0.0
        threshold = baseline * 0.20  # 20% cumulative deviation triggers alert
        min_display_change_pct = 5.0

        for i in range(half, len(amounts)):
            deviation = amounts[i] - baseline
            cusum_pos = max(0, cusum_pos + deviation)
            cusum_neg = min(0, cusum_neg + deviation)

            if cusum_pos > threshold:
                # Price increase detected
                new_avg = mean(amounts[i:]) if i < len(amounts) else amounts[i]
                change_pct = ((new_avg - baseline) / baseline) * 100
                if change_pct < min_display_change_pct:
                    continue

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
                if abs(change_pct) < min_display_change_pct:
                    continue

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

_NON_SUBSCRIPTION_KEYWORDS = {
    "transfer to", "transfer from", "funds transfer", "third party trf",
    "itb-customer tran", "service charge", "gct", "govt tax",
    "tax on service charge",
}

_VARIABLE_SPEND_KEYWORDS = {
    "uber", "trip", "taxi", "ride", "rideshare", "knutsford", "airbnb",
    "hotel", "restaurant", "grocery", "supermarket",
}

_MERCHANT_PREFIXES = (
    "pos purchase", "online purchase", "card purchase", "debit card",
    "visa purchase", "mastercard purchase",
)

_LOCATION_WORDS = {
    "kingston", "jamaica", "stockholm", "mountain", "view", "us", "se",
    "nl", "dublin", "vorden", "ann", "st", "ltd", "inc", "llc", "ab",
    "co", "com", "for",
}

_BILLING_PERIODS = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "quarterly": 90,
    "yearly": 365,
}


def _description(tx: dict) -> str:
    return (tx.get("description") or "").strip()


def _is_excluded_transaction(tx: dict) -> bool:
    """Return True for bank movements, fees, and tax rows."""
    desc_lower = _description(tx).lower()
    return any(keyword in desc_lower for keyword in _NON_SUBSCRIPTION_KEYWORDS)


def _is_variable_spend(tx: dict) -> bool:
    desc_lower = _description(tx).lower()
    return any(keyword in desc_lower for keyword in _VARIABLE_SPEND_KEYWORDS)


def _known_subscription_name(description: str) -> str | None:
    desc_lower = description.lower()
    for keyword, name in _SUBSCRIPTION_KEYWORDS.items():
        if keyword in desc_lower:
            return name
    return None


def _clean_merchant_name(description: str) -> str:
    """Normalize bank descriptions enough to group recurring merchant rows."""
    known = _known_subscription_name(description)
    if known:
        return known

    cleaned = description.lower()
    for prefix in _MERCHANT_PREFIXES:
        cleaned = re.sub(rf"^{re.escape(prefix)}\s+", "", cleaned)
    cleaned = re.sub(r"\bfor\s+\d{2}[a-z]{3}\d{2}\b", " ", cleaned)
    cleaned = re.sub(r"\b[a-z]*\d+[a-z0-9]*\b", " ", cleaned)
    cleaned = re.sub(r"[^a-z&+ ]+", " ", cleaned)
    words = [
        word for word in cleaned.split()
        if len(word) > 1 and word not in _LOCATION_WORDS
    ]
    if not words:
        return description.strip()
    return " ".join(words[:4]).title()


def _is_merchant_like_debit(tx: dict) -> bool:
    desc_lower = _description(tx).lower()
    return (
        tx.get("debit", 0) > 0
        and not tx.get("excluded_from_subscription_analysis", False)
        and not _is_variable_spend(tx)
        and (
            tx.get("category") == "subscription"
            or any(desc_lower.startswith(prefix) for prefix in _MERCHANT_PREFIXES)
        )
    )


def _is_subscription_candidate(tx: dict) -> bool:
    """Only real merchant debits should feed subscription-style detectors."""
    return _is_merchant_like_debit(tx)


def _dedupe_raw_transactions(transactions: list[dict]) -> list[dict]:
    """Remove duplicate rows from overlapping statements while preserving order."""
    seen = set()
    deduped = []

    for tx in transactions:
        amount = tx.get("amount", 0) or 0
        balance = tx.get("balance")
        key = (
            tx.get("date"),
            (tx.get("description") or "").strip().lower(),
            round(float(amount), 2),
            round(float(balance), 2) if isinstance(balance, (int, float)) else None,
            tx.get("currency", "JMD"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tx)

    return deduped


def _classify_transactions(transactions: list[dict]) -> list[dict]:
    """Add category and vendor_name fields to transactions."""
    for tx in transactions:
        desc_lower = (tx.get("description") or "").lower()
        vendor_name = tx.get("description", "")
        category = "other"

        excluded = _is_excluded_transaction(tx)

        if not excluded:
            known_name = _known_subscription_name(desc_lower)
            if known_name:
                category = "subscription"
                vendor_name = known_name
            elif tx.get("debit", 0) > 0 and any(
                desc_lower.startswith(prefix) for prefix in _MERCHANT_PREFIXES
            ):
                category = "merchant"
                vendor_name = _clean_merchant_name(tx.get("description", ""))

        tx["category"] = category
        tx["vendor_name"] = vendor_name
        tx["excluded_from_subscription_analysis"] = excluded

    return transactions


def _find_possible_subscriptions(classified_txs: list[dict]) -> list[dict]:
    """Known subscription merchants with one eligible charge need more history."""
    vendor_groups: dict[str, list[dict]] = defaultdict(list)
    for tx in classified_txs:
        if _is_subscription_candidate(tx):
            vendor = (tx.get("vendor_name") or tx["description"]).strip()
            vendor_groups[vendor].append(tx)

    possible = []
    for vendor, charges in vendor_groups.items():
        if len(charges) != 1:
            continue

        charge = charges[0]
        if charge.get("category") != "subscription":
            continue
        date_str = charge["date"]
        if isinstance(date_str, datetime):
            date_str = date_str.strftime("%Y-%m-%d")

        possible.append({
            "merchant": vendor,
            "amount": round(charge["debit"], 2),
            "period": "unknown",
            "period_days": None,
            "confidence": 0.4,
            "confidence_label": "possible",
            "charge_count": 1,
            "last_charge": date_str,
            "reason": "Known subscription merchant, but only one eligible charge was found.",
        })

    possible.sort(key=lambda item: item["merchant"].lower())
    return possible


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

def _classify_recurring_period(charges: list[dict]) -> dict | None:
    """Find a recurring interval by date gaps, allowing skipped cycles."""
    if len(charges) < 2:
        return None

    dates = [charge["date"] for charge in sorted(charges, key=lambda t: t["date"])]
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    if not gaps:
        return None

    best = None
    for label, period_days in _BILLING_PERIODS.items():
        matches = 0
        missed_cycles = 0
        normalized_gaps = []

        for gap in gaps:
            cycles = max(1, round(gap / period_days))
            expected = cycles * period_days
            tolerance = max(3, round(period_days * 0.25))
            if abs(gap - expected) <= tolerance:
                matches += 1
                missed_cycles += max(0, cycles - 1)
                normalized_gaps.append(gap / cycles)

        match_ratio = matches / len(gaps)
        if matches < 2 and not (len(charges) == 2 and matches == 1):
            continue
        if match_ratio < 0.45:
            continue

        score = match_ratio + (0.08 if len(charges) >= 3 else 0) - (0.03 * missed_cycles)
        candidate = {
            "period": label,
            "period_days": round(median(normalized_gaps or [period_days]), 1),
            "match_ratio": match_ratio,
            "missed_cycles": missed_cycles,
            "score": score,
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    return best


def _amount_stability(amounts: list[float]) -> float:
    if len(amounts) < 2:
        return 1.0
    avg = mean(amounts)
    if avg == 0:
        return 0.0
    avg_abs_deviation = mean(abs(amount - avg) for amount in amounts)
    return max(0.0, 1 - (avg_abs_deviation / avg))


def _run_subscription_detection(classified_txs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Convert engine transactions → classmate's Transaction objects,
    run detect_subscriptions(), return (subscriptions, renewal_predictions).
    """
    # Build Detection Transactions from eligible merchant debits only.
    detection_txs = []
    for tx in classified_txs:
        if _is_subscription_candidate(tx):
            detection_txs.append(DetectionTransaction(
                date=tx["date"],
                amount=tx["debit"],
                merchant=tx.get("vendor_name") or tx["description"],
            ))

    if not detection_txs:
        return [], []

    with redirect_stdout(StringIO()):
        detected_subs = _detect_subs(detection_txs, min_occurrences=2)

    subscriptions = []
    renewal_predictions = []
    today = datetime.now()

    for sub in detected_subs:
        display_confidence = sub.confidence
        if len(sub.transactions) == 2:
            display_confidence = min(display_confidence, 0.8)

        # Determine typical renewal day-of-month
        days = [t.date.day if hasattr(t.date, "day") else t.date
                for t in sub.transactions]
        renewal_day = max(set(days), key=days.count) if days else 1

        subscriptions.append({
            "merchant": sub.merchant,
            "amount": round(sub.avg_amount, 2),
            "period": sub.period or "unknown",
            "period_days": sub.period_days,
            "confidence": display_confidence,
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

            period_days = int(sub.period_days or 30)
            stale_grace = timedelta(days=max(7, round(period_days * 0.5)))
            if next_date < today - stale_grace:
                continue

            days_until = (next_date - today).days

            if display_confidence >= 0.8:
                conf_label = "high"
            elif display_confidence >= 0.5:
                conf_label = "medium"
            else:
                conf_label = "low"

            band = max(2, round((1 - display_confidence) * 10))

            renewal_predictions.append({
                "subscription": sub.merchant,
                "next_charge_date": next_date.strftime("%Y-%m-%d"),
                "days_until_charge": days_until,
                "period": sub.period,
                "period_days": sub.period_days,
                "confidence": display_confidence,
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


def _run_subscription_detection(classified_txs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Detect recurring merchant charges by cadence first.

    Amount changes should create price-change context, not block recurrence.
    """
    merchant_groups: dict[str, list[dict]] = defaultdict(list)
    for tx in classified_txs:
        if _is_subscription_candidate(tx):
            merchant = (tx.get("vendor_name") or _clean_merchant_name(tx["description"])).strip()
            merchant_groups[merchant].append(tx)

    subscriptions = []
    renewal_predictions = []
    today = datetime.now()

    for merchant, charges in merchant_groups.items():
        if len(charges) < 2:
            continue

        sorted_charges = sorted(charges, key=lambda t: t["date"])
        is_known_subscription = sorted_charges[0].get("category") == "subscription"
        if not is_known_subscription and len(sorted_charges) < 3:
            continue

        period_info = _classify_recurring_period(sorted_charges)
        if not period_info:
            continue

        amounts = [charge["debit"] for charge in sorted_charges]
        stability = _amount_stability(amounts)
        data_score = min(1.0, len(sorted_charges) / 4)
        display_confidence = min(
            0.98,
            (period_info["match_ratio"] * 0.70) + (stability * 0.15) + (data_score * 0.15),
        )
        if len(sorted_charges) == 2:
            display_confidence = min(display_confidence, 0.8)

        days = [charge["date"].day for charge in sorted_charges]
        renewal_day = max(set(days), key=days.count) if days else 1
        last_charge = sorted_charges[-1]["date"]
        avg_amount = median(amounts)

        subscriptions.append({
            "merchant": merchant,
            "amount": round(avg_amount, 2),
            "period": period_info["period"],
            "period_days": period_info["period_days"],
            "confidence": display_confidence,
            "charge_count": len(sorted_charges),
            "renewal_day": renewal_day,
            "last_charge": last_charge.strftime("%Y-%m-%d"),
            "amount_stability": round(stability, 3),
            "missed_cycles": period_info["missed_cycles"],
            "needs_review": not is_known_subscription,
            "raw_merchant": sorted_charges[0].get("description", ""),
        })

        next_date = last_charge + timedelta(days=int(round(period_info["period_days"] or 30)))
        stale_grace = timedelta(days=max(7, round((period_info["period_days"] or 30) * 0.5)))
        if next_date < today - stale_grace:
            continue

        days_until = (next_date - today).days
        if display_confidence >= 0.8:
            conf_label = "high"
        elif display_confidence >= 0.5:
            conf_label = "medium"
        else:
            conf_label = "low"

        band = max(2, round((1 - display_confidence) * 10))
        renewal_predictions.append({
            "subscription": merchant,
            "next_charge_date": next_date.strftime("%Y-%m-%d"),
            "days_until_charge": days_until,
            "period": period_info["period"],
            "period_days": period_info["period_days"],
            "confidence": display_confidence,
            "confidence_label": conf_label,
            "confidence_window": {
                "earliest": (next_date - timedelta(days=band)).strftime("%Y-%m-%d"),
                "latest": (next_date + timedelta(days=band)).strftime("%Y-%m-%d"),
                "band_days": band,
            },
            "data_points": len(sorted_charges),
            "last_charge_date": last_charge.strftime("%Y-%m-%d"),
        })

    renewal_predictions.sort(key=lambda p: p["days_until_charge"])
    subscriptions.sort(key=lambda s: (s.get("needs_review", False), s["merchant"].lower()))
    return subscriptions, renewal_predictions


# =====================================================================
# Free trial detection (Capstone trial_classifier)
# =====================================================================

def _detect_trials(classified_txs: list[dict]) -> list[dict]:
    """
    Group transactions by vendor, run trial classifier on each group.
    Returns list of merchants flagged as likely free trial → paid conversions.
    """
    # Group by eligible subscription-like merchant charges only.
    vendor_groups: dict[str, list[dict]] = defaultdict(list)
    for tx in classified_txs:
        if _is_subscription_candidate(tx):
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
        if len({t["date"] for t in txns}) < 2:
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

def _build_subscription_analysis(raw_transactions: list[dict], dedupe: bool = False) -> dict:
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
    if not raw_transactions:
        return {"error": "No transactions found in the PDF. Check the statement format."}

    if dedupe:
        raw_transactions = _dedupe_raw_transactions(raw_transactions)

    # Detect bank/currency from raw output
    banks = sorted({tx.get("bank", "Unknown") for tx in raw_transactions})
    currencies = sorted({tx.get("currency", "JMD") for tx in raw_transactions})
    bank_detected = ", ".join(banks)
    currency_detected = currencies[0] if len(currencies) == 1 else "Mixed"

    # Convert format
    transactions = _convert_to_engine_format(raw_transactions)
    if not transactions:
        return {"error": "Could not parse any valid transactions from the PDF."}

    transactions.sort(key=lambda tx: tx["date"])
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
    possible_subscriptions = _find_possible_subscriptions(classified)
    logger.info(f"Step 3 complete: {len(subscriptions)} subscription(s), "
                f"{len(possible_subscriptions)} possible, "
                f"{len(renewal_predictions)} prediction(s)")

    # 4. Detect free trials
    logger.info("Step 4: Detecting free trials...")
    trial_alerts = _detect_trials(classified)
    logger.info(f"Step 4 complete: {len(trial_alerts)} trial alert(s)")

    # 5. Detect price changes
    logger.info("Step 5: Detecting price changes...")
    confirmed_merchants = {sub["merchant"] for sub in subscriptions}
    price_changes = _detect_price_changes(classified, confirmed_merchants)
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
        "possible_subscriptions": possible_subscriptions,
        "renewal_predictions": renewal_predictions,
        "trial_alerts": trial_alerts,
        "price_changes": price_changes,
        "currency_summary": currency_summary,
        "summary": {
            "total_subscriptions": len(subscriptions),
            "total_possible_subscriptions": len(possible_subscriptions),
            "total_sub_cost": round(total_sub_cost, 2),
            "total_trial_alerts": len(trial_alerts),
            "total_price_changes": len(price_changes),
            "total_debits": round(sum(tx["debit"] for tx in classified), 2),
            "total_credits": round(sum(tx["credit"] for tx in classified), 2),
        },
    }


def analyze_subscriptions(file_bytes: bytes) -> dict:
    """
    Main entry point: takes PDF bytes, returns full subscription analysis.
    """
    logger.info("Step 1: Extracting transactions...")
    raw_transactions = extract_from_bytes(file_bytes)
    return _build_subscription_analysis(raw_transactions)


def analyze_extracted_subscriptions(raw_transactions: list[dict]) -> dict:
    """Analyze pre-extracted transactions from one or more statements."""
    return _build_subscription_analysis(raw_transactions, dedupe=True)
