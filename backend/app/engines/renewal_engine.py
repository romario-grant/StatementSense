"""
RenewalSense Engine — Pure functions for renewal risk analysis.
Stripped of CLI code, ready for API integration.
"""

import os
import io
import math
import csv
import re
import logging
from datetime import datetime

# ── Universal extractor (capstone_revised) ─────────────────────────
# Falls back to the legacy Scotiabank-only parser if this import fails
# (e.g. missing camelot dependency in some environments).
try:
    from capstone_revised.extract_transactions import extract_from_bytes as _universal_extract
    _HAS_UNIVERSAL = True
except ImportError:
    _HAS_UNIVERSAL = False

# ── Classmate’s subscription detection algorithm ───────────────
try:
    from subscription_detection_alg import (
        Transaction as DetectionTransaction,
        detect_subscriptions as _detect_subs,
    )
    _HAS_DETECTION_ALG = True
except ImportError:
    _HAS_DETECTION_ALG = False

logger = logging.getLogger(__name__)


# ==========================================
# 1. BANK STATEMENT PARSER (PDF + CSV)
# ==========================================

class StatementParser:
    """Extracts transactions from bank statements (PDF + CSV).
    
    Uses the universal extractor (capstone_revised) — works with ANY bank.
    """
    
    @staticmethod
    def _convert_universal_to_engine_format(universal_txs):
        """
        Convert capstone_revised output format into the dict format expected
        by the downstream classifier/detector pipeline.
        
        capstone_revised outputs:
            {bank, date (str), description, amount (signed float), balance, currency, source_file}
        
        Engine expects:
            {date (datetime), description, debit (float), credit (float), balance (float)}
        """
        converted = []
        for tx in universal_txs:
            # Parse date string → datetime
            date_val = tx.get("date")
            if isinstance(date_val, str):
                try:
                    date_val = datetime.strptime(date_val, "%Y-%m-%d")
                except ValueError:
                    continue  # Skip unparseable dates
            elif not isinstance(date_val, datetime):
                continue
            
            # Split signed amount → debit / credit
            amount = tx.get("amount", 0) or 0
            if amount < 0:
                debit = abs(amount)
                credit = 0
            else:
                debit = 0
                credit = amount
            
            balance = tx.get("balance") or 0
            
            converted.append({
                "date": date_val,
                "description": tx.get("description", ""),
                "debit": debit,
                "credit": credit,
                "balance": balance,
            })
        
        return converted
    
    @staticmethod
    def parse_pdf_bytes(file_bytes):
        """
        Parse PDF from bytes (for file upload).
        Uses the universal extractor (capstone_revised) — works with any bank.
        """
        if not _HAS_UNIVERSAL:
            logger.error("capstone_revised module not available — cannot extract transactions")
            return []
        
        try:
            logger.info("Using universal extractor (capstone_revised)...")
            universal_txs = _universal_extract(file_bytes)
            if universal_txs:
                converted = StatementParser._convert_universal_to_engine_format(universal_txs)
                if converted:
                    logger.info(f"Universal extractor found {len(converted)} transactions")
                    return converted
                else:
                    logger.warning("Universal extractor returned data but conversion produced 0 rows")
            else:
                logger.warning("Universal extractor returned 0 transactions")
        except Exception as e:
            logger.error(f"Universal extractor failed: {e}")
        
        return []



# ==========================================
# 2. RULE-BASED TRANSACTION CLASSIFIER
# ==========================================

class RuleBasedClassifier:
    """Classifies transactions using keyword matching. No AI required."""
    
    SUBSCRIPTION_KEYWORDS = {
        'netflix': 'Netflix', 'spotify': 'Spotify', 'youtube': 'YouTube',
        'youtubepremium': 'YouTube Premium', 'disney': 'Disney+',
        'hulu': 'Hulu', 'hbo': 'HBO Max', 'paramount': 'Paramount+',
        'peacock': 'Peacock', 'crunchyroll': 'Crunchyroll',
        'apple music': 'Apple Music', 'apple tv': 'Apple TV+',
        'amazon prime': 'Amazon Prime', 'audible': 'Audible',
        'tidal': 'Tidal', 'deezer': 'Deezer', 'pandora': 'Pandora',
        'icloud': 'iCloud', 'google one': 'Google One',
        'google storage': 'Google Storage', 'dropbox': 'Dropbox',
        'microsoft 365': 'Microsoft 365', 'office 365': 'Office 365',
        'adobe': 'Adobe', 'canva': 'Canva',
        'playstation': 'PlayStation', 'xbox': 'Xbox',
        'nintendo': 'Nintendo', 'steam': 'Steam',
        'chatgpt': 'ChatGPT', 'openai': 'OpenAI',
        'notion': 'Notion', 'grammarly': 'Grammarly',
        'duolingo': 'Duolingo', 'headspace': 'Headspace',
        'calm': 'Calm', 'tinder': 'Tinder', 'bumble': 'Bumble',
        'flow': 'Flow', 'digicel': 'Digicel',
    }
    
    TRANSACTION_PATTERNS = {
        'POS PURCHASE': 'shopping',
        'ABM WITHDRAWAL': 'atm_withdrawal',
        'ATM WITHDRAWAL': 'atm_withdrawal',
        'FUNDS TRANSFER FROM': 'transfer',
        'FUNDS TRANSFER TO': 'transfer',
        'FUNDS TRANSFER': 'transfer',
        'ITB-CUSTOMER TRAN': 'transfer',
        'THIRD PARTY TRF': 'transfer',
        'BILL PAYMENT': 'utilities',
        'LOAN PAYMENT': 'loan_payment',
        'MORTGAGE': 'loan_payment',
        'INSURANCE': 'insurance',
    }
    
    VENDOR_KEYWORDS = {
        'knutsford': 'transport', 'uber': 'transport', 'lyft': 'transport',
        'bolt': 'transport', 'taxi': 'transport', 'shell': 'transport',
        'texaco': 'transport', 'rubis': 'transport',
        'juici': 'dining', 'kfc': 'dining', 'burger king': 'dining',
        'mcdonalds': 'dining', 'dominos': 'dining', 'pizza': 'dining',
        'restaurant': 'dining', 'minimart': 'dining', 'food': 'dining',
        'bakery': 'dining', 'cafe': 'dining', 'grill': 'dining',
        'patties': 'dining', 'island grill': 'dining',
        'supermarket': 'groceries', 'hi-lo': 'groceries',
        'pricesmart': 'groceries', 'megamart': 'groceries',
        'jps': 'utilities', 'jamaica public service': 'utilities',
        'nwc': 'utilities', 'national water': 'utilities',
        'pharmacy': 'health', 'hospital': 'health', 'medical': 'health',
        'uwi': 'education', 'university': 'education',
        'rent': 'rent', 'landlord': 'rent',
    }
    
    def classify(self, transactions):
        """Classify each transaction. Returns the same list with added fields."""
        for tx in transactions:
            desc = tx.get('description', '').upper()
            desc_lower = desc.lower()
            
            category = 'other'
            is_subscription = False
            is_recurring = False
            vendor_name = tx.get('description', '')
            
            # Skip subscription detection for bill payments (utilities like Flow, Digicel)
            is_bill_payment = 'BILL PAYMENT' in desc
            if not is_bill_payment:
                for keyword, name in self.SUBSCRIPTION_KEYWORDS.items():
                    if keyword in desc_lower:
                        category = 'subscription'
                        is_subscription = True
                        is_recurring = True
                        vendor_name = name
                        break
            
            if not is_subscription:
                for pattern, cat in self.TRANSACTION_PATTERNS.items():
                    if pattern in desc:
                        category = cat
                        break
            
            if category in ('shopping', 'other'):
                for keyword, cat in self.VENDOR_KEYWORDS.items():
                    if keyword in desc_lower:
                        category = cat
                        vendor_name = keyword.title()
                        break
            
            if tx['credit'] > 0 and category in ('transfer', 'other'):
                if tx['credit'] >= 10000:
                    category = 'salary'
                    is_recurring = True
            
            if 'ABM' in desc or 'ATM' in desc:
                category = 'atm_withdrawal'
            
            # Auto-flag recurring expense categories
            if category in ('utilities', 'loan_payment', 'insurance', 'rent'):
                is_recurring = True
            
            tx['category'] = category
            tx['is_subscription'] = is_subscription
            tx['is_recurring'] = is_recurring
            tx['vendor_name'] = vendor_name
        
        return transactions


# ==========================================
# 3. PATTERN DETECTOR
# ==========================================

class PatternDetector:
    """Detects salary, subscriptions, and expenses from classified transactions."""
    
    @staticmethod
    def detect_salary(transactions):
        credits = [tx for tx in transactions if tx.get("category") == "salary" or tx["credit"] > 0]
        if not credits:
            return None
        
        amount_groups = {}
        for tx in credits:
            amount = tx["credit"]
            if amount <= 0:
                continue
            matched = False
            for key in amount_groups:
                if abs(amount - key) / key < 0.05:
                    amount_groups[key].append(tx)
                    matched = True
                    break
            if not matched:
                amount_groups[amount] = [tx]
        
        if not amount_groups:
            return None
        
        # Require at least 2 occurrences to qualify as salary
        amount_groups = {k: v for k, v in amount_groups.items() if len(v) >= 2}
        if not amount_groups:
            return None
        
        # Prioritize occurrence count (most frequent), then total amount as tiebreaker
        best_group = max(amount_groups.items(), key=lambda x: (len(x[1]), sum(t["credit"] for t in x[1])))
        salary_txs = best_group[1]
        avg_amount = sum(tx["credit"] for tx in salary_txs) / len(salary_txs)
        
        days = [tx["date"].day for tx in salary_txs if isinstance(tx["date"], datetime)]
        pay_day = max(set(days), key=days.count) if days else 25
        # Calculate actual interval between deposits to determine frequency
        if len(salary_txs) >= 2:
            dates = sorted([tx["date"] for tx in salary_txs if isinstance(tx["date"], datetime)])
            if len(dates) >= 2:
                intervals = [(dates[i+1] - dates[i]).days for i in range(len(dates)-1)]
                avg_interval = sum(intervals) / len(intervals)
                frequency = "biweekly" if avg_interval <= 18 else "monthly"
            else:
                frequency = "monthly"
        else:
            frequency = "monthly"
        
        return {
            "amount": round(avg_amount, 2),
            "pay_day": pay_day,
            "frequency": frequency,
            "occurrences": len(salary_txs)
        }
    
    @staticmethod
    def detect_subscriptions(transactions):
        subs = [tx for tx in transactions if tx.get("is_subscription")]
        if not subs:
            return []
        
        vendor_groups = {}
        for tx in subs:
            vendor = tx.get("vendor_name", tx["description"]).lower().strip()
            if vendor not in vendor_groups:
                vendor_groups[vendor] = []
            vendor_groups[vendor].append(tx)
        
        detected = []
        for vendor, txs in vendor_groups.items():
            avg_amount = sum(tx["debit"] for tx in txs) / len(txs)
            days = [tx["date"].day for tx in txs if isinstance(tx["date"], datetime)]
            if not days:
                continue
            
            expected_day = max(set(days), key=days.count)
            failures = sum(1 for d in days if abs(d - expected_day) > 2)
            display_name = txs[0].get("vendor_name", vendor).title()
            
            detected.append({
                "name": display_name,
                "amount": round(avg_amount, 2),
                "renewal_day": expected_day,
                "past_failures": failures,
                "total_months": len(txs),
                "fail_rate": failures / max(len(txs), 1)
            })
        
        return detected
    
    @staticmethod
    def detect_expenses(transactions):
        expense_categories = {"rent", "utilities", "loan_payment", "insurance"}
        expenses = [
            tx for tx in transactions
            if tx.get("category") in expense_categories
            and tx.get("is_recurring", False) and tx["debit"] > 0
        ]
        
        vendor_groups = {}
        for tx in expenses:
            vendor = tx.get("vendor_name", tx["description"]).lower().strip()
            if vendor not in vendor_groups:
                vendor_groups[vendor] = []
            vendor_groups[vendor].append(tx)
        
        detected = []
        for vendor, txs in vendor_groups.items():
            avg_amount = sum(tx["debit"] for tx in txs) / len(txs)
            days = [tx["date"].day for tx in txs if isinstance(tx["date"], datetime)]
            if not days:
                continue
            typical_day = max(set(days), key=days.count)
            display_name = txs[0].get("vendor_name", vendor).title()
            detected.append({"name": display_name, "amount": round(avg_amount, 2), "day": typical_day})
        
        return detected


# ==========================================
# 3.5 PRICE CHANGE & TRIAL CONVERSION (6.5)
# ==========================================

class PriceChangeDetector:
    """
    Applies CUSUM (Cumulative Sum Control Chart) to the time-series of 
    transaction amounts for each subscription to detect structural billing changes.
    
    Detects:
    - Trial → Paid conversion (e.g., $0 → $9.99)
    - Silent price increases (e.g., $1,200 → $1,450)
    - Plan upgrades/downgrades (large magnitude shifts)
    - Anomalies (one-off spikes that revert)
    """
    
    @staticmethod
    def detect_price_changes(transactions):
        """
        Takes the full classified transaction list, groups subscription 
        transactions by vendor, runs CUSUM on each vendor's amount series.
        Returns a list of detected change events.
        """
        # Group subscription transactions by vendor, sorted by date
        subs = [tx for tx in transactions if tx.get("is_subscription") and tx["debit"] > 0]
        
        vendor_groups = {}
        for tx in subs:
            vendor = tx.get("vendor_name", tx["description"]).lower().strip()
            if vendor not in vendor_groups:
                vendor_groups[vendor] = []
            vendor_groups[vendor].append(tx)
        
        all_changes = []
        
        for vendor, txs in vendor_groups.items():
            # Need at least 2 transactions to detect a change
            if len(txs) < 2:
                continue
            
            # Sort by date
            txs_sorted = sorted(txs, key=lambda t: t["date"])
            amounts = [tx["debit"] for tx in txs_sorted]
            dates = [tx["date"] for tx in txs_sorted]
            display_name = txs_sorted[0].get("vendor_name", vendor).title()
            
            # --- Direct pairwise comparison (catches obvious shifts) ---
            for i in range(1, len(amounts)):
                prev = amounts[i - 1]
                curr = amounts[i]
                
                if prev == 0 and curr > 0:
                    # Trial → Paid
                    all_changes.append({
                        "subscription": display_name,
                        "type": "Trial Conversion",
                        "date": dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], 'strftime') else str(dates[i]),
                        "old_amount": round(prev, 2),
                        "new_amount": round(curr, 2),
                        "change_amount": round(curr - prev, 2),
                        "change_percent": 100.0,
                        "severity": "info",
                        "description": f"Free trial ended. Now billing ${curr:.2f}/cycle."
                    })
                elif prev > 0 and curr > 0 and abs(curr - prev) / prev > 0.05:
                    # More than 5% change
                    change_pct = ((curr - prev) / prev) * 100
                    change_amt = curr - prev
                    
                    if change_pct > 0:
                        # Price went up
                        severity = "warning" if change_pct > 20 else "info"
                        
                        # Determine type based on magnitude
                        if change_pct > 50:
                            change_type = "Plan Upgrade"
                            desc = f"Significant price jump: ${prev:.2f} → ${curr:.2f} (+{change_pct:.0f}%). Likely a plan change."
                        else:
                            change_type = "Price Increase"
                            desc = f"Price increased from ${prev:.2f} to ${curr:.2f} (+{change_pct:.1f}%)."
                    else:
                        # Price went down
                        severity = "info"
                        if abs(change_pct) > 50:
                            change_type = "Plan Downgrade"
                            desc = f"Significant price drop: ${prev:.2f} → ${curr:.2f} ({change_pct:.0f}%). Likely a plan change."
                        else:
                            change_type = "Price Decrease"
                            desc = f"Price decreased from ${prev:.2f} to ${curr:.2f} ({change_pct:.1f}%)."
                    
                    all_changes.append({
                        "subscription": display_name,
                        "type": change_type,
                        "date": dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], 'strftime') else str(dates[i]),
                        "old_amount": round(prev, 2),
                        "new_amount": round(curr, 2),
                        "change_amount": round(change_amt, 2),
                        "change_percent": round(change_pct, 1),
                        "severity": severity,
                        "description": desc
                    })
            
            # --- CUSUM for sustained drift detection ---
            # This catches gradual creep that pairwise might miss across many cycles
            if len(amounts) >= 3:
                cusum_changes = PriceChangeDetector._run_cusum(amounts, dates, display_name)
                # Only add CUSUM findings that aren't already caught by pairwise
                existing_dates = {c["date"] for c in all_changes if c["subscription"] == display_name}
                for cc in cusum_changes:
                    if cc["date"] not in existing_dates:
                        all_changes.append(cc)
        
        # Sort by date
        all_changes.sort(key=lambda c: c["date"])
        return all_changes
    
    @staticmethod
    def _run_cusum(amounts, dates, display_name, threshold_factor=1.5):
        """
        CUSUM algorithm on billing amounts.
        Accumulates deviations from baseline mean; flags when cumulative sum exceeds threshold.
        """
        mean = sum(amounts) / len(amounts)
        std = (sum((x - mean) ** 2 for x in amounts) / len(amounts)) ** 0.5
        
        if std == 0:
            return []  # All amounts identical — no change possible
        
        threshold = threshold_factor * std
        cusum_pos = 0.0
        cusum_neg = 0.0
        changes = []
        
        for i, amount in enumerate(amounts):
            cusum_pos = max(0, cusum_pos + (amount - mean) - 0.5 * std)
            cusum_neg = max(0, cusum_neg + (mean - amount) - 0.5 * std)
            
            if cusum_pos > threshold:
                date_str = dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], 'strftime') else str(dates[i])
                changes.append({
                    "subscription": display_name,
                    "type": "Sustained Price Drift (Up)",
                    "date": date_str,
                    "old_amount": round(mean, 2),
                    "new_amount": round(amount, 2),
                    "change_amount": round(amount - mean, 2),
                    "change_percent": round(((amount - mean) / mean) * 100, 1) if mean > 0 else 0,
                    "severity": "warning",
                    "description": f"CUSUM detected sustained upward drift. Baseline: ${mean:.2f}, Current: ${amount:.2f}."
                })
                cusum_pos = 0  # Reset after detection
            
            if cusum_neg > threshold:
                date_str = dates[i].strftime("%Y-%m-%d") if hasattr(dates[i], 'strftime') else str(dates[i])
                changes.append({
                    "subscription": display_name,
                    "type": "Sustained Price Drift (Down)",
                    "date": date_str,
                    "old_amount": round(mean, 2),
                    "new_amount": round(amount, 2),
                    "change_amount": round(amount - mean, 2),
                    "change_percent": round(((amount - mean) / mean) * 100, 1) if mean > 0 else 0,
                    "severity": "info",
                    "description": f"CUSUM detected sustained downward drift. Baseline: ${mean:.2f}, Current: ${amount:.2f}."
                })
                cusum_neg = 0  # Reset after detection
        
        return changes


# ==========================================
# 3.6 RENEWAL TIME PREDICTION (6.4)
# ==========================================

class RenewalPredictor:
    """
    Predicts when each subscription will next be billed using:
    - Median inter-transaction interval (robust to outliers)
    - IQR-based confidence band (narrow = reliable, wide = erratic)
    - Cold-start handling (< 3 charges → 30-day default prior)
    
    Output per subscription:
    - next_charge_date: estimated date of next billing
    - days_until_charge: countdown from today
    - confidence_window: [earliest, latest] dates
    - confidence_label: "high" / "medium" / "low"
    """
    
    @staticmethod
    def predict_renewals(transactions, today=None):
        """
        Takes classified transactions, groups by subscription vendor,
        computes median interval + IQR for each.
        """
        if today is None:
            today = datetime.now()
        
        subs = [tx for tx in transactions if tx.get("is_subscription") and tx["debit"] > 0]
        
        vendor_groups = {}
        for tx in subs:
            vendor = tx.get("vendor_name", tx["description"]).lower().strip()
            if vendor not in vendor_groups:
                vendor_groups[vendor] = []
            vendor_groups[vendor].append(tx)
        
        predictions = []
        
        for vendor, txs in vendor_groups.items():
            txs_sorted = sorted(txs, key=lambda t: t["date"])
            dates = [tx["date"] for tx in txs_sorted]
            display_name = txs_sorted[0].get("vendor_name", vendor).title()
            last_charge = dates[-1]
            num_charges = len(dates)
            
            if num_charges < 2:
                # Cold-start: only 1 charge → assume 30-day cycle
                median_interval = 30
                confidence_days = 7  # Wide band — low confidence
                confidence_label = "low"
                method = "cold_start"
            elif num_charges < 3:
                # 2 charges — use actual interval but flag as medium confidence
                interval = (dates[1] - dates[0]).days
                median_interval = interval if interval > 0 else 30
                confidence_days = 5
                confidence_label = "medium"
                method = "single_interval"
            else:
                # 3+ charges — full median + IQR
                intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
                intervals = [iv for iv in intervals if iv > 0]  # Remove zero/negative
                
                if not intervals:
                    median_interval = 30
                    confidence_days = 7
                    confidence_label = "low"
                    method = "fallback"
                else:
                    intervals_sorted = sorted(intervals)
                    n = len(intervals_sorted)
                    
                    # Median
                    if n % 2 == 0:
                        median_interval = (intervals_sorted[n // 2 - 1] + intervals_sorted[n // 2]) / 2
                    else:
                        median_interval = intervals_sorted[n // 2]
                    
                    # IQR
                    q1_idx = n // 4
                    q3_idx = (3 * n) // 4
                    q1 = intervals_sorted[q1_idx]
                    q3 = intervals_sorted[min(q3_idx, n - 1)]
                    iqr = q3 - q1
                    
                    # Confidence band = ±(1.5 × IQR), minimum ±2 days
                    confidence_days = max(round(1.5 * iqr), 2)
                    
                    # Label based on IQR width relative to median
                    if iqr <= 2:
                        confidence_label = "high"
                    elif iqr <= 7:
                        confidence_label = "medium"
                    else:
                        confidence_label = "low"
                    
                    method = "median_iqr"
            
            # Calculate next charge date
            from datetime import timedelta
            next_charge = last_charge + timedelta(days=int(median_interval))
            
            # If predicted date is in the past, advance by one interval
            while next_charge < today:
                next_charge += timedelta(days=int(median_interval))
            
            days_until = (next_charge - today).days
            
            # Confidence window
            earliest = next_charge - timedelta(days=confidence_days)
            latest = next_charge + timedelta(days=confidence_days)
            
            predictions.append({
                "subscription": display_name,
                "next_charge_date": next_charge.strftime("%Y-%m-%d"),
                "days_until_charge": days_until,
                "median_interval_days": round(median_interval, 1),
                "confidence_window": {
                    "earliest": earliest.strftime("%Y-%m-%d"),
                    "latest": latest.strftime("%Y-%m-%d"),
                    "band_days": confidence_days
                },
                "confidence_label": confidence_label,
                "method": method,
                "data_points": num_charges,
                "last_charge_date": last_charge.strftime("%Y-%m-%d")
            })
        
        # Sort by days_until_charge (soonest first)
        predictions.sort(key=lambda p: p["days_until_charge"])
        return predictions


# ==========================================
# 4. RISK SCORE ENGINE
# ==========================================

class SalaryCycleTracker:
    def __init__(self, salary_amount, pay_day, frequency="monthly"):
        self.salary_amount = salary_amount
        self.pay_day = pay_day
        self.frequency = frequency
    
    def days_since_payday(self, day):
        return day - self.pay_day if day >= self.pay_day else (30 - self.pay_day) + day
    
    def days_until_payday(self, day):
        return self.pay_day - day if day < self.pay_day else (30 - day) + self.pay_day
    
    def paycycle_position(self, day):
        days_since = self.days_since_payday(day)
        cycle_length = 30 if self.frequency == "monthly" else 14
        return min(days_since / cycle_length, 1.0)
    
    def get_zone(self, day):
        pos = self.paycycle_position(day)
        if pos <= 0.3: return "SAFE ZONE", "safe"
        if pos <= 0.6: return "MID-CYCLE", "moderate"
        if pos <= 0.8: return "CAUTION ZONE", "high"
        return "DANGER ZONE", "critical"


class ExpenseProfiler:
    def __init__(self, expenses=None):
        self.expenses = expenses or []
    
    def add_expense(self, name, amount, day):
        self.expenses.append({"name": name, "amount": amount, "day": day})
    
    def total_monthly_expenses(self):
        return sum(e["amount"] for e in self.expenses)
    
    def expenses_before_day(self, target_day):
        return sum(e["amount"] for e in self.expenses if e["day"] <= target_day)
    
    def cluster_penalty(self, target_day, window=3):
        total = 0
        for e in self.expenses:
            distance = min(abs(e["day"] - target_day), 30 - abs(e["day"] - target_day))
            if distance <= window:
                total += e["amount"]
        return total
    
    def expense_load_ratio(self, target_day, salary):
        spent = self.expenses_before_day(target_day)
        return min(spent / salary, 1.0) if salary > 0 else 0.5


class RiskScoreEngine:
    def __init__(self):
        self.w_paycycle = 0.35
        self.w_cluster = 0.25
        self.w_history = 0.25
        self.w_load = 0.15
    
    def calculate_risk(self, subscription, salary_tracker, expense_profiler):
        day = subscription["renewal_day"]
        
        paycycle_factor = salary_tracker.paycycle_position(day)
        cluster_amount = expense_profiler.cluster_penalty(day)
        cluster_factor = min(cluster_amount / salary_tracker.salary_amount, 1.0) if salary_tracker.salary_amount > 0 else 0.5
        fail_rate = subscription.get("fail_rate", 0.0)
        load_factor = expense_profiler.expense_load_ratio(day, salary_tracker.salary_amount)
        
        raw = (self.w_paycycle * paycycle_factor + self.w_cluster * cluster_factor +
               self.w_history * fail_rate + self.w_load * load_factor)
        
        risk_score = 1 / (1 + math.exp(-8 * (raw - 0.45)))
        risk_score = round(risk_score, 2)
        
        if risk_score <= 0.30:
            label, level = "LOW", "low"
            advice = "Your renewal should go through fine."
        elif risk_score <= 0.55:
            label, level = "MODERATE", "moderate"
            advice = "Check your balance a day before renewal."
        elif risk_score <= 0.75:
            label, level = "HIGH", "high"
            advice = "High risk of insufficient funds. Transfer money to your card."
        else:
            label, level = "CRITICAL", "critical"
            advice = "This renewal will likely fail. Add funds immediately."
        
        zone_label, zone_level = salary_tracker.get_zone(day)
        
        return {
            "subscription": subscription["name"],
            "amount": subscription["amount"],
            "renewal_day": day,
            "risk_score": risk_score,
            "risk_label": label,
            "risk_level": level,
            "advice": advice,
            "fail_history": f"{subscription.get('past_failures', 0)}/{subscription.get('total_months', 4)}",
            "breakdown": {
                "paycycle_factor": round(paycycle_factor, 2),
                "cluster_factor": round(cluster_factor, 2),
                "fail_rate": round(fail_rate, 2),
                "load_factor": round(load_factor, 2),
                "zone_label": zone_label,
                "zone_level": zone_level,
                "days_since_payday": salary_tracker.days_since_payday(day),
                "days_until_payday": salary_tracker.days_until_payday(day),
                "cluster_amount": round(cluster_amount, 2)
            }
        }


# ==========================================
# 5. MAIN ANALYSIS FUNCTION
# ==========================================

def analyze_statement(file_bytes):
    """
    Main entry point: takes PDF bytes, returns full analysis.
    This is what the API endpoint calls.
    """
    # Parse transactions
    transactions = StatementParser.parse_pdf_bytes(file_bytes)
    if not transactions:
        return {"error": "No transactions found in the PDF. Check the statement format."}
    
    # Classify (categories, vendor names, etc.)
    classifier = RuleBasedClassifier()
    classified = classifier.classify(transactions)
    
    # Count categories
    categories = {}
    for tx in classified:
        cat = tx.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1
    
    # Detect patterns
    salary_info = PatternDetector.detect_salary(classified)
    expenses = PatternDetector.detect_expenses(classified)
    
    # ── Subscription detection ──────────────────────────────────────
    # Use classmate's subscription_detection_alg if available,
    # otherwise fall back to built-in PatternDetector.
    if _HAS_DETECTION_ALG:
        logger.info("Using classmate's subscription detection algorithm")
        subscriptions, renewal_predictions = _run_classmate_detection(classified)
    else:
        logger.info("subscription_detection_alg not available, using built-in detector")
        subscriptions = PatternDetector.detect_subscriptions(classified)
        renewal_predictions = RenewalPredictor.predict_renewals(classified)
    
    if not salary_info:
        return {
            "error": "Could not detect salary pattern. Need more statement data.",
            "transactions_parsed": len(transactions),
            "categories": categories
        }
    
    # Build expense profiler
    expense_profiler = ExpenseProfiler()
    for e in expenses:
        expense_profiler.add_expense(e["name"], e["amount"], e["day"])
    
    # Calculate risk for each subscription
    salary_tracker = SalaryCycleTracker(
        salary_info["amount"], salary_info["pay_day"], salary_info["frequency"]
    )
    
    risk_engine = RiskScoreEngine()
    risk_results = []
    for sub in subscriptions:
        result = risk_engine.calculate_risk(sub, salary_tracker, expense_profiler)
        risk_results.append(result)
    
    risk_results.sort(key=lambda r: r["risk_score"], reverse=True)
    
    # Build paycycle map (30 days)
    paycycle_map = []
    for d in range(1, 31):
        pos = salary_tracker.paycycle_position(d)
        zone_label, zone_level = salary_tracker.get_zone(d)
        is_payday = d == salary_info["pay_day"]
        
        # Check if any subscription renews on this day
        sub_on_day = None
        for sub in subscriptions:
            if sub["renewal_day"] == d:
                sub_on_day = sub["name"]
                break
        
        paycycle_map.append({
            "day": d,
            "position": round(pos, 2),
            "zone": zone_level,
            "is_payday": is_payday,
            "subscription": sub_on_day
        })
    
    # Transaction list for display (serializable)
    tx_list = []
    for tx in classified:
        tx_list.append({
            "date": tx["date"].strftime("%Y-%m-%d") if isinstance(tx["date"], datetime) else str(tx["date"]),
            "description": tx["description"],
            "debit": tx["debit"],
            "credit": tx["credit"],
            "category": tx.get("category", "other"),
            "vendor_name": tx.get("vendor_name", ""),
            "is_subscription": tx.get("is_subscription", False)
        })
    
    total_sub_cost = sum(r["amount"] for r in risk_results)
    total_expenses = expense_profiler.total_monthly_expenses()
    high_risk_count = sum(1 for r in risk_results if r["risk_level"] in ("high", "critical"))
    
    # 6.5 — Price Change & Trial Conversion Detection (CUSUM)
    price_changes = PriceChangeDetector.detect_price_changes(classified)
    
    return {
        "transactions_parsed": len(transactions),
        "categories": categories,
        "salary": salary_info,
        "subscriptions": risk_results,
        "expenses": expenses,
        "paycycle_map": paycycle_map,
        "transactions": tx_list,
        "price_changes": price_changes,
        "renewal_predictions": renewal_predictions,
        "summary": {
            "total_subscriptions": len(risk_results),
            "high_risk_count": high_risk_count,
            "total_sub_cost": round(total_sub_cost, 2),
            "total_expenses": round(total_expenses, 2),
            "income_remaining": round(salary_info["amount"] - total_expenses - total_sub_cost, 2)
        }
    }


def _run_classmate_detection(classified_transactions):
    """
    Convert engine transactions → classmate's Transaction objects,
    run detect_subscriptions(), and map results back to the API format
    expected by the frontend (subscriptions list + renewal_predictions list).
    """
    from datetime import timedelta

    # Convert to classmate's Transaction format
    # The algorithm needs: date (date/datetime), amount (float), merchant (str)
    # We only pass debits (outgoing money) since subscriptions are charges
    detection_txs = []
    for tx in classified_transactions:
        if tx["debit"] > 0:
            detection_txs.append(DetectionTransaction(
                date=tx["date"] if isinstance(tx["date"], datetime) else datetime.strptime(str(tx["date"]), "%Y-%m-%d"),
                amount=tx["debit"],
                merchant=tx.get("vendor_name") or tx["description"],
            ))
    
    if not detection_txs:
        return [], []
    
    # Run classmate's detection algorithm
    detected_subs = _detect_subs(detection_txs, min_occurrences=2)
    
    # Map to the format expected by the risk engine and API
    subscriptions = []
    renewal_predictions = []
    today = datetime.now()
    
    for sub in detected_subs:
        # Determine the typical renewal day-of-month
        days = [t.date.day if hasattr(t.date, 'day') else t.date for t in sub.transactions]
        renewal_day = max(set(days), key=days.count) if days else 1
        
        # Count "failures" (charges that were far from the expected day)
        failures = sum(1 for d in days if abs(d - renewal_day) > 3)
        
        subscriptions.append({
            "name": sub.merchant,
            "amount": round(sub.avg_amount, 2),
            "renewal_day": renewal_day,
            "past_failures": failures,
            "total_months": len(sub.transactions),
            "fail_rate": failures / max(len(sub.transactions), 1),
        })
        
        # Build renewal prediction from classmate's algorithm
        next_due = sub.next_expected()
        if next_due is not None:
            # Ensure next_due is in the future
            if isinstance(next_due, datetime):
                next_date = next_due
            else:
                next_date = datetime.combine(next_due, datetime.min.time())
            
            while next_date < today:
                next_date += timedelta(days=int(sub.period_days or 30))
            
            days_until = (next_date - today).days
            
            # Confidence label from classmate's confidence score
            if sub.confidence >= 0.8:
                conf_label = "high"
            elif sub.confidence >= 0.5:
                conf_label = "medium"
            else:
                conf_label = "low"
            
            # Confidence window (tighter for higher confidence)
            band = max(2, round((1 - sub.confidence) * 10))
            earliest = next_date - timedelta(days=band)
            latest = next_date + timedelta(days=band)
            
            renewal_predictions.append({
                "subscription": sub.merchant,
                "next_charge_date": next_date.strftime("%Y-%m-%d"),
                "days_until_charge": days_until,
                "median_interval_days": sub.period_days or 30,
                "confidence_window": {
                    "earliest": earliest.strftime("%Y-%m-%d"),
                    "latest": latest.strftime("%Y-%m-%d"),
                    "band_days": band,
                },
                "confidence_label": conf_label,
                "method": f"classmate_alg_{sub.period or 'unknown'}",
                "data_points": len(sub.transactions),
                "last_charge_date": max(t.date for t in sub.transactions).strftime("%Y-%m-%d") if sub.transactions else None,
            })
    
    # Sort predictions by soonest first
    renewal_predictions.sort(key=lambda p: p["days_until_charge"])
    
    logger.info(f"Classmate's algorithm detected {len(subscriptions)} subscription(s), {len(renewal_predictions)} prediction(s)")
    return subscriptions, renewal_predictions

