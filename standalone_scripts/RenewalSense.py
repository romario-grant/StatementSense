"""Command-line implementation of RenewalSense. Parses a bank statement, infers the pay cycle, detects recurring expenses, and prints a renewal-risk report."""

import os
import math
import csv
import re
from datetime import datetime
from dotenv import load_dotenv

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

# ==========================================
# 1. Bank statement parser
# ==========================================

class StatementParser:
    """Parse bank statements supplied as either PDF or CSV. PDF parsing delegates to the shared backend extraction pipeline so the CLI and API produce identical transaction shapes."""
    
    @staticmethod
    def parse_pdf(file_path):
        """Extract transactions from a PDF bank statement via the shared extractor."""
        
        if not os.path.exists(file_path):
            print(f"  File not found: {file_path}")
            return []
        
        try:
            import sys
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)
            from backend.app.extraction.extract_transactions import extract_from_pdf

            universal_rows = extract_from_pdf(file_path)
            converted = StatementParser._convert_universal_rows(universal_rows)
            if converted:
                return converted
        except Exception as e:
            print(f"  PDF extraction error: {e}")

        return []

    @staticmethod
    def _convert_universal_rows(rows):
        converted = []
        for tx in rows or []:
            date_val = tx.get("date")
            if isinstance(date_val, str):
                try:
                    date_val = datetime.strptime(date_val, "%Y-%m-%d")
                except ValueError:
                    continue
            elif not isinstance(date_val, datetime):
                continue
            amount = float(tx.get("amount") or 0)
            converted.append({
                "date": date_val,
                "description": tx.get("description", ""),
                "debit": abs(amount) if amount < 0 else 0.0,
                "credit": amount if amount > 0 else 0.0,
                "balance": float(tx.get("balance") or 0),
            })
        return converted
    
    @staticmethod
    def parse_csv(file_path):
        """Parses a CSV bank statement."""
        if not os.path.exists(file_path):
            print(f"  File not found: {file_path}")
            return []
        
        transactions = []
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Match common bank-export columns without depending on header casing.
                    normalized = {k.lower().strip(): v.strip() for k, v in row.items() if v}
                    
                    date_str = (normalized.get('date') or normalized.get('transaction date') 
                                or normalized.get('post date') or normalized.get('value date') or "")
                    
                    desc = (normalized.get('description') or normalized.get('details') 
                            or normalized.get('narrative') or normalized.get('particulars') or "")
                    
                    debit = StatementParser._parse_amount(
                        normalized.get('debit') or normalized.get('withdrawal') 
                        or normalized.get('dr') or ""
                    )
                    credit = StatementParser._parse_amount(
                        normalized.get('credit') or normalized.get('deposit') 
                        or normalized.get('cr') or ""
                    )
                    
                    # Single-amount exports encode debits as negative values.
                    if debit == 0 and credit == 0:
                        amount_str = normalized.get('amount', '')
                        amount = StatementParser._parse_amount(amount_str)
                        if amount < 0:
                            debit = abs(amount)
                        elif amount > 0:
                            credit = amount
                    
                    balance = StatementParser._parse_amount(
                        normalized.get('balance') or normalized.get('running balance') or ""
                    )
                    
                    parsed_date = StatementParser._parse_date(date_str)
                    
                    if parsed_date and (debit > 0 or credit > 0):
                        transactions.append({
                            "date": parsed_date,
                            "description": desc,
                            "debit": debit,
                            "credit": credit,
                            "balance": balance
                        })
        
        except Exception as e:
            print(f"  CSV parsing error: {e}")
        
        return transactions
    
    @staticmethod
    def _parse_date(date_str):
        """Tries multiple date formats to parse a date string."""
        if not date_str:
            return None
        
        date_str = date_str.strip()
        formats = [
            "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y",
            "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
            "%d/%m/%y", "%m/%d/%y", "%Y/%m/%d"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        return None
    
    @staticmethod
    def _parse_amount(amount_str):
        """Parses an amount string, handling commas, currency symbols, etc."""
        if not amount_str:
            return 0
        
        # Remove currency symbols before numeric conversion.
        cleaned = re.sub(r'[^0-9.,\-]', '', str(amount_str))
        cleaned = cleaned.replace(',', '')
        
        try:
            return abs(float(cleaned))
        except ValueError:
            return 0

# ==========================================
# 2. Rule-based transaction classifier
# ==========================================

class RuleBasedClassifier:
    """Classify bank transactions into categories using keyword matching against a curated dictionary of well-known subscription and vendor names."""

    # Known subscription services keyed by case-insensitive description substrings.
    SUBSCRIPTION_KEYWORDS = {
        # Streaming
        'netflix': 'Netflix', 'spotify': 'Spotify', 'youtube': 'YouTube',
        'youtubepremium': 'YouTube Premium', 'disney': 'Disney+',
        'hulu': 'Hulu', 'hbo': 'HBO Max', 'paramount': 'Paramount+',
        'peacock': 'Peacock', 'crunchyroll': 'Crunchyroll',
        'apple music': 'Apple Music', 'apple tv': 'Apple TV+',
        'amazon prime': 'Amazon Prime', 'audible': 'Audible',
        'tidal': 'Tidal', 'deezer': 'Deezer', 'pandora': 'Pandora',
        
        # Cloud / Tech
        'icloud': 'iCloud', 'google one': 'Google One',
        'google storage': 'Google Storage', 'dropbox': 'Dropbox',
        'microsoft 365': 'Microsoft 365', 'office 365': 'Office 365',
        'adobe': 'Adobe', 'canva': 'Canva',
        
        # Gaming
        'playstation': 'PlayStation', 'xbox': 'Xbox',
        'nintendo': 'Nintendo', 'steam': 'Steam',
        'ea play': 'EA Play', 'epic games': 'Epic Games',
        
        # Apps & Services
        'chatgpt': 'ChatGPT', 'openai': 'OpenAI',
        'notion': 'Notion', 'evernote': 'Evernote',
        'grammarly': 'Grammarly', 'duolingo': 'Duolingo',
        'headspace': 'Headspace', 'calm': 'Calm',
        'tinder': 'Tinder', 'bumble': 'Bumble',
        
        # Jamaican services
        'flow': 'Flow', 'digicel': 'Digicel',
        'jps': 'JPS', 'nwc': 'NWC',
        'lampa': 'Lampa',
    }
    
    # Common statement descriptors used to identify transfer and bill rows.
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
    
    # Known vendor categories (Jamaican + international)
    VENDOR_KEYWORDS = {
        # Transport
        'knutsford': 'transport', 'uber': 'transport', 'lyft': 'transport',
        'bolt': 'transport', 'taxi': 'transport', 'gas station': 'transport',
        'shell': 'transport', 'texaco': 'transport', 'total': 'transport',
        'rubis': 'transport',
        
        # Dining / Food
        'juici': 'dining', 'kfc': 'dining', 'burger king': 'dining',
        'mcdonalds': 'dining', 'dominos': 'dining', 'pizza': 'dining',
        'restaurant': 'dining', 'minimart': 'dining', 'food': 'dining',
        'bakery': 'dining', 'cafe': 'dining', 'grill': 'dining',
        'patties': 'dining', 'island grill': 'dining',
        
        # Groceries
        'supermarket': 'groceries', 'hi-lo': 'groceries',
        'pricesmart': 'groceries', 'shoppers fair': 'groceries',
        'megamart': 'groceries', 'progressive': 'groceries',
        'loshusan': 'groceries', 'general food': 'groceries',
        
        # Utilities (Jamaica)
        'jps': 'utilities', 'jamaica public service': 'utilities',
        'nwc': 'utilities', 'national water': 'utilities',
        'flow': 'utilities', 'digicel': 'utilities',
        'lime': 'utilities',
        
        # Health
        'pharmacy': 'health', 'hospital': 'health', 'clinic': 'health',
        'doctor': 'health', 'medical': 'health', 'dental': 'health',
        
        # Education
        'uwi': 'education', 'university': 'education',
        'school': 'education', 'college': 'education',
        
        # Rent
        'rent': 'rent', 'landlord': 'rent',
    }
    
    def classify_transactions(self, transactions):
        """Classifies each transaction using keyword rules."""
        if not transactions:
            return []
        
        for tx in transactions:
            desc = tx.get('description', '').upper()
            
            # Default classification
            category = 'other'
            is_subscription = False
            is_recurring = False
            vendor_name = tx.get('description', '')
            
            # --- Step 1: Check if it's a known subscription ---
            # Skip subscription detection for bill payments (utilities like Flow, Digicel)
            desc_lower = desc.lower()
            is_bill_payment = 'BILL PAYMENT' in desc
            if not is_bill_payment:
                for keyword, name in self.SUBSCRIPTION_KEYWORDS.items():
                    if keyword in desc_lower:
                        category = 'subscription'
                        is_subscription = True
                        is_recurring = True
                        vendor_name = name
                        break
            
            # --- Step 2: Check transaction type patterns ---
            if not is_subscription:
                for pattern, cat in self.TRANSACTION_PATTERNS.items():
                    if pattern in desc:
                        category = cat
                        break
            
            # --- Step 3: Check vendor keywords (for POS purchases) ---
            if category == 'shopping' or category == 'other':
                for keyword, cat in self.VENDOR_KEYWORDS.items():
                    if keyword in desc_lower:
                        category = cat
                        # Clean up vendor name
                        vendor_name = keyword.title()
                        break
            
            # --- Step 4: Identify credits as potential salary ---
            if tx['credit'] > 0 and category in ['transfer', 'other']:
                # Large credits that aren't small transfers are potential salary
                if tx['credit'] >= 10000:  # J$10,000+ threshold
                    category = 'salary'
                    is_recurring = True
            
            # --- Step 5: ATM withdrawals ---
            if 'ABM' in desc or 'ATM' in desc:
                category = 'atm_withdrawal'
            
            # --- Step 6: Auto-flag recurring expense categories ---
            if category in ('utilities', 'loan_payment', 'insurance', 'rent'):
                is_recurring = True
            
            # Apply classification
            tx['category'] = category
            tx['is_subscription'] = is_subscription
            tx['is_recurring'] = is_recurring
            tx['vendor_name'] = vendor_name
        
        return transactions

# ==========================================
# 3. Pattern detector
# ==========================================

class PatternDetector:
    """Analyze classified transactions to infer salary cadence, recurring subscriptions, and recurring non-subscription expenses such as rent and utilities."""
    
    @staticmethod
    def detect_salary(transactions):
        """Finds the salary deposit pattern (largest recurring credit)."""
        credits = [tx for tx in transactions if tx.get("category") == "salary" or tx["credit"] > 0]
        
        if not credits:
            return None
        
        # Group by similar amounts (within 5% tolerance)
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
        
        # Detect pay day (most common day of month)
        days = [tx["date"].day for tx in salary_txs if isinstance(tx["date"], datetime)]
        if days:
            pay_day = max(set(days), key=days.count)
        else:
            pay_day = 25  # Default assumption
        
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
        """
        Finds recurring subscription charges.
        Also detects failed renewals (same subscription appearing on different dates).
        """
        subs = [tx for tx in transactions if tx.get("is_subscription") or tx.get("category") == "subscription"]
        
        if not subs:
            return []
        
        # Group by vendor name
        vendor_groups = {}
        for tx in subs:
            vendor = tx.get("vendor_name", tx["description"]).lower().strip()
            if vendor not in vendor_groups:
                vendor_groups[vendor] = []
            vendor_groups[vendor].append(tx)
        
        detected = []
        for vendor, txs in vendor_groups.items():
            if len(txs) < 1:
                continue
            
            avg_amount = sum(tx["debit"] for tx in txs) / len(txs)
            
            # Detect renewal day (most common day)
            days = [tx["date"].day for tx in txs if isinstance(tx["date"], datetime)]
            if not days:
                continue
            
            expected_day = max(set(days), key=days.count)
            
            # Detect failed renewals: if a charge appears on a different day
            # than expected, the original attempt likely failed
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
        """Finds recurring non-subscription expenses (rent, utilities, loans)."""
        expense_categories = {"rent", "utilities", "loan_payment", "insurance"}
        
        expenses = [
            tx for tx in transactions 
            if tx.get("category") in expense_categories 
            and tx.get("is_recurring", False) 
            and tx["debit"] > 0
        ]
        
        # Group by vendor
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
            
            detected.append({
                "name": display_name,
                "amount": round(avg_amount, 2),
                "day": typical_day
            })
        
        return detected

# ==========================================
# 4. Salary cycle tracker
# ==========================================

class SalaryCycleTracker:
    """
    Tracks the salary deposit pattern to map out the paycheck cycle.
    """
    
    def __init__(self, salary_amount, pay_day, frequency="monthly"):
        self.salary_amount = salary_amount
        self.pay_day = pay_day
        self.frequency = frequency
    
    def days_since_payday(self, day_of_month):
        if day_of_month >= self.pay_day:
            return day_of_month - self.pay_day
        else:
            return (30 - self.pay_day) + day_of_month
    
    def days_until_payday(self, day_of_month):
        if day_of_month < self.pay_day:
            return self.pay_day - day_of_month
        else:
            return (30 - day_of_month) + self.pay_day
    
    def paycycle_position(self, day_of_month):
        """0.0 = just paid, 1.0 = day before next payday."""
        days_since = self.days_since_payday(day_of_month)
        cycle_length = 30 if self.frequency == "monthly" else 14
        return min(days_since / cycle_length, 1.0)
    
    def get_zone(self, day_of_month):
        position = self.paycycle_position(day_of_month)
        if position <= 0.3:
            return "SAFE ZONE", "ðŸŸ¢"
        elif position <= 0.6:
            return "MID-CYCLE", "ðŸŸ¡"
        elif position <= 0.8:
            return "CAUTION ZONE", "ðŸŸ "
        else:
            return "DANGER ZONE", "ðŸ”´"

# ==========================================
# 5. Expense profiler
# ==========================================

class ExpenseProfiler:
    """Maps recurring expenses throughout the month."""
    
    def __init__(self):
        self.expenses = []
    
    def add_expense(self, name, amount, day_of_month):
        self.expenses.append({"name": name, "amount": amount, "day": day_of_month})
    
    def total_monthly_expenses(self):
        return sum(e["amount"] for e in self.expenses)
    
    def expenses_before_day(self, target_day):
        return sum(e["amount"] for e in self.expenses if e["day"] <= target_day)
    
    def cluster_penalty(self, target_day, window=3):
        cluster_total = 0
        for e in self.expenses:
            distance = abs(e["day"] - target_day)
            distance = min(distance, 30 - distance)
            if distance <= window:
                cluster_total += e["amount"]
        return cluster_total
    
    def expense_load_ratio(self, target_day, salary_amount):
        spent = self.expenses_before_day(target_day)
        return min(spent / salary_amount, 1.0) if salary_amount > 0 else 0.5

# ==========================================
# 6. Risk score engine
# ==========================================

class RiskScoreEngine:
    """
    Combines 4 signals into a Risk Score (0.0 to 1.0):
    
    Risk = wâ‚ x PaycycleFactor + wâ‚‚ x ClusterPenalty 
         + wâ‚ƒ x HistoricalFailRate + wâ‚„ x ExpenseLoadFactor
    """
    
    def __init__(self):
        self.w_paycycle = 0.35
        self.w_cluster = 0.25
        self.w_history = 0.25
        self.w_load = 0.15
    
    def calculate_risk(self, subscription, salary_tracker, expense_profiler):
        renewal_day = subscription["renewal_day"]
        sub_amount = subscription["amount"]
        
        paycycle_factor = salary_tracker.paycycle_position(renewal_day)
        
        cluster_amount = expense_profiler.cluster_penalty(renewal_day, window=3)
        cluster_factor = min(cluster_amount / salary_tracker.salary_amount, 1.0) if salary_tracker.salary_amount > 0 else 0.5
        
        fail_rate = subscription.get("fail_rate", 0.0)
        
        load_factor = expense_profiler.expense_load_ratio(renewal_day, salary_tracker.salary_amount)
        
        raw_score = (
            self.w_paycycle * paycycle_factor +
            self.w_cluster * cluster_factor +
            self.w_history * fail_rate +
            self.w_load * load_factor
        )
        
        risk_score = 1 / (1 + math.exp(-8 * (raw_score - 0.45)))
        risk_score = round(risk_score, 2)
        
        if risk_score <= 0.30:
            risk_label, risk_icon = "LOW", "ðŸŸ¢"
            advice = "Your renewal should go through fine."
        elif risk_score <= 0.55:
            risk_label, risk_icon = "MODERATE", "ðŸŸ¡"
            advice = "Check your balance a day before renewal."
        elif risk_score <= 0.75:
            risk_label, risk_icon = "HIGH", "ðŸŸ "
            advice = "âš  High risk of insufficient funds. Transfer money to your card."
        else:
            risk_label, risk_icon = "CRITICAL", "ðŸ”´"
            advice = "ðŸš¨ This renewal will likely fail. Add funds immediately."
        
        zone_label, zone_icon = salary_tracker.get_zone(renewal_day)
        
        return {
            "subscription": subscription["name"],
            "amount": sub_amount,
            "renewal_day": renewal_day,
            "risk_score": risk_score,
            "risk_label": risk_label,
            "risk_icon": risk_icon,
            "advice": advice,
            "fail_history": f"{subscription.get('past_failures', 0)}/{subscription.get('total_months', 4)} months failed",
            "breakdown": {
                "paycycle_factor": round(paycycle_factor, 2),
                "cluster_factor": round(cluster_factor, 2),
                "fail_rate": round(fail_rate, 2),
                "load_factor": round(load_factor, 2),
                "zone_label": zone_label,
                "zone_icon": zone_icon,
                "days_since_payday": salary_tracker.days_since_payday(renewal_day),
                "days_until_payday": salary_tracker.days_until_payday(renewal_day),
                "cluster_amount": round(cluster_amount, 2)
            }
        }

# ==========================================
# 7. Pay-cycle visualiser
# ==========================================

def draw_paycycle_bar(salary_tracker, subscriptions):
    """Draws a visual 30-day bar showing payday, zones, and renewal positions."""
    pay_day = salary_tracker.pay_day
    
    print(f"\n  â”Œâ”€ 30-DAY PAYCYCLE MAP (Payday: Day {pay_day}) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”")
    
    bar = [" "] * 30
    bar[pay_day - 1] = "$"
    
    sub_markers = {}
    for i, sub in enumerate(subscriptions):
        day = sub["renewal_day"] - 1
        if 0 <= day < 30:
            marker = str(i + 1)
            bar[day] = marker
            sub_markers[marker] = sub["name"]
    
    zone_bar = ""
    for d in range(30):
        actual_day = d + 1
        pos = salary_tracker.paycycle_position(actual_day)
        char = bar[d]
        if char == "$":
            zone_bar += "ðŸ’°"
        elif char != " ":
            zone_bar += f"[{char}]"
        else:
            if pos <= 0.3:
                zone_bar += "â–ˆ"
            elif pos <= 0.6:
                zone_bar += "â–“"
            elif pos <= 0.8:
                zone_bar += "â–’"
            else:
                zone_bar += "â–‘"
    
    print(f"  â”‚ {zone_bar}")
    print(f"  â”‚ â–ˆ Safe  â–“ Mid  â–’ Caution  â–‘ Danger  ðŸ’° Payday")
    
    for marker, name in sub_markers.items():
        print(f"  â”‚ [{marker}] = {name}")
    
    print(f"  â””{'â”€' * 48}â”˜")

# ==========================================
# 8. Interactive command-line entry point
# ==========================================

def run_app():
    print("=========================================")
    print("  RenewalSense - Smart Renewal Alerts    ")
    print("=========================================")
    run_statement_mode()

def run_statement_mode():
    """Statement upload mode - parses PDFs/CSVs and auto-detects everything."""
    
    # Initialize rule-based classifier (no AI needed)
    classifier = RuleBasedClassifier()
    print("  OK Rule-based classifier ready (no AI required)")
    
    # --- Collect Statement Files via Windows File Picker ---
    print("\n[Step 1: Select your bank statements]")
    print("  A file picker will open - select 1-4 PDF or CSV bank statements.\n")
    
    import tkinter as tk
    from tkinter import filedialog
    
    root = tk.Tk()
    root.withdraw()  # Hide the main tkinter window
    root.attributes('-topmost', True)  # Bring dialog to front
    
    file_paths = filedialog.askopenfilenames(
        title="Select Bank Statements (1-4 files)",
        filetypes=[
            ("Bank Statements", "*.pdf *.csv *.txt"),
            ("PDF Files", "*.pdf"),
            ("CSV Files", "*.csv"),
            ("All Files", "*.*")
        ],
        initialdir=os.path.expanduser("~")
    )
    
    root.destroy()
    
    if not file_paths:
        print("  x No files selected.")
        return
    
    # Limit to 4 files
    file_paths = file_paths[:4]
    
    all_transactions = []
    file_count = 0
    
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"  x File not found: {file_path}")
            continue
        
        # Parse based on extension
        ext = os.path.splitext(file_path)[1].lower()
        file_name = os.path.basename(file_path)
        
        if ext == '.pdf':
            print(f"  [Parsing {file_name}...]")
            txs = StatementParser.parse_pdf(file_path)
        elif ext in ['.csv', '.txt']:
            print(f"  [Parsing {file_name}...]")
            txs = StatementParser.parse_csv(file_path)
        else:
            print(f"  x Unsupported format: {ext}. Use PDF or CSV.")
            continue
        
        if txs:
            all_transactions.extend(txs)
            file_count += 1
            print(f"  OK Parsed {len(txs)} transactions from {file_name}")
        else:
            print(f"  x No transactions found in {file_name}.")
    
    if not all_transactions:
        print("\n  No transactions parsed. Check your statement format.")
        return
    
    # --- Classify Transactions ---
    print(f"\n[Step 2: Classifying {len(all_transactions)} transactions...]")
    classified = classifier.classify_transactions(all_transactions)
    
    # Count categories
    categories = {}
    for tx in classified:
        cat = tx.get("category", "other")
        categories[cat] = categories.get(cat, 0) + 1
    
    print("  OK Classification complete:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat.replace('_', ' ').title():20s} {count} transactions")
    
    # --- Auto-detect Patterns ---
    print(f"\n[Step 3: Detecting financial patterns...]")
    
    # Detect salary
    salary_info = PatternDetector.detect_salary(classified)
    if salary_info:
        print(f"  OK Salary detected: ${salary_info['amount']:,.2f} on day {salary_info['pay_day']} ({salary_info['frequency']})")
        salary_tracker = SalaryCycleTracker(
            salary_info['amount'], salary_info['pay_day'], salary_info['frequency']
        )
    else:
        print("  x Could not auto-detect salary. Please enter manually:")
        salary_amount = float(input("    Monthly salary: $"))
        pay_day = int(input("    Payday (day of month): "))
        salary_tracker = SalaryCycleTracker(salary_amount, pay_day)
    
    # Detect subscriptions  
    subs = PatternDetector.detect_subscriptions(classified)
    if subs:
        print(f"\n  OK Detected {len(subs)} subscription(s):")
        for s in subs:
            fail_str = f" ({s['past_failures']} failed)" if s['past_failures'] > 0 else ""
            print(f"    â€¢ {s['name']} - ${s['amount']:.2f}/mo on day {s['renewal_day']}{fail_str}")
    else:
        print("  x No subscriptions auto-detected.")
        return
    
    # Detect expenses
    expenses = PatternDetector.detect_expenses(classified)
    expense_profiler = ExpenseProfiler()
    if expenses:
        print(f"\n  OK Detected {len(expenses)} recurring expense(s):")
        for e in expenses:
            expense_profiler.add_expense(e['name'], e['amount'], e['day'])
            print(f"    â€¢ {e['name']} - ${e['amount']:,.2f} on day {e['day']}")
    else:
        print("  â„¹ No major recurring expenses detected.")
    
    # --- Run Risk Analysis ---
    run_risk_analysis(salary_tracker, expense_profiler, subs)



def run_risk_analysis(salary_tracker, expense_profiler, subscriptions):
    """Shared risk analysis and display for both modes."""
    
    # --- Paycycle Map ---
    draw_paycycle_bar(salary_tracker, subscriptions)
    
    # --- Calculate Risk ---
    print("\n[Calculating renewal risk scores...]\n")
    
    risk_engine = RiskScoreEngine()
    results = []
    
    for sub in subscriptions:
        result = risk_engine.calculate_risk(sub, salary_tracker, expense_profiler)
        results.append(result)
    
    results.sort(key=lambda r: r["risk_score"], reverse=True)
    
    # --- Display Report ---
    print("=========================================")
    print("  RENEWALSENSE RISK REPORT")
    print("=========================================")
    
    high_risk_count = 0
    
    for i, res in enumerate(results):
        bd = res["breakdown"]
        
        print(f"\n  --- {res['subscription']} ---")
        print(f"  Amount:        ${res['amount']:.2f}")
        print(f"  Renewal Day:   Day {res['renewal_day']} {bd['zone_icon']} ({bd['zone_label']})")
        print(f"  Risk Score:    {res['risk_icon']} {res['risk_score']:.0%} ({res['risk_label']})")
        print(f"  Fail History:  {res['fail_history']}")
        
        print(f"\n  Risk Breakdown:")
        print(f"    Paycycle:    {bd['days_since_payday']} days after payday, {bd['days_until_payday']} days until next ({bd['paycycle_factor']:.0%})")
        print(f"    Clustering:  ${bd['cluster_amount']:.2f} in expenses within Â±3 days ({bd['cluster_factor']:.0%})")
        print(f"    Load:        {bd['load_factor']:.0%} of salary consumed by day {res['renewal_day']}")
        print(f"    History:     {bd['fail_rate']:.0%} failure rate")
        
        if res['risk_label'] in ['HIGH', 'CRITICAL']:
            high_risk_count += 1
            print(f"\n  âš¡ ALERT: {res['advice']}")
        else:
            print(f"\n  â„¹  {res['advice']}")
        
        print(f"  {'â”€' * 40}")
    
    # --- Summary ---
    total_expenses = expense_profiler.total_monthly_expenses()
    total_sub_cost = sum(r["amount"] for r in results)
    
    print(f"\n  â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•")
    print(f"  SUMMARY")
    print(f"  â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•")
    print(f"  Total subscriptions:   {len(results)}")
    print(f"  High-risk renewals:    {high_risk_count}")
    print(f"  Total sub spending:    ${total_sub_cost:,.2f}/mo")
    print(f"  Income remaining:      ${salary_tracker.salary_amount - total_expenses - total_sub_cost:,.2f}/mo (after expenses + subs)")
    
    if high_risk_count > 0:
        print(f"\n  ðŸš¨ You have {high_risk_count} high-risk renewal(s).")
        print(f"  Set reminders to check your balance the day before.")
    else:
        print(f"\n  âœ… All renewals are in a safe zone. You're good!")
    
    print()

if __name__ == "__main__":
    run_app()
