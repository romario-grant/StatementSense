import os
import math
import json
import csv
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# 1. BANK STATEMENT PARSER (PDF + CSV)
# ==========================================

class StatementParser:
    """
    Extracts transactions from bank statements.
    Supports PDF (via pdfplumber) and CSV formats.
    
    PDF parsing currently supports:
    - Scotia Bank Jamaica format (DDMON Description J$ Amount +/-)
    
    CSV parsing supports:
    - Any CSV with Date, Description, Debit/Credit columns
    """
    
    @staticmethod
    def parse_pdf(file_path):
        """
        Extracts transactions from a PDF bank statement.
        Optimized for Jamaican bank formats (Scotia, NCB, JMMB).
        
        Scotia format: "DDMON DESCRIPTION J$ AMOUNT +/- [J$ BALANCE]"
        """
        import pdfplumber
        
        if not os.path.exists(file_path):
            print(f"  ✗ File not found: {file_path}")
            return []
        
        transactions = []
        
        # Determine statement year from the file
        statement_year = datetime.now().year
        
        try:
            with pdfplumber.open(file_path) as pdf:
                # First pass: try to find statement period for year
                first_page_text = pdf.pages[0].extract_text() or ""
                year_match = re.search(r'Statement Period:.*?(\d{2}[A-Z]{3})(\d{2})\s+to\s+(\d{2}[A-Z]{3})(\d{2})', first_page_text)
                if year_match:
                    end_year_short = year_match.group(4)
                    statement_year = 2000 + int(end_year_short)
                
                # Extract text from all pages and parse transactions
                for page in pdf.pages:
                    text = page.extract_text()
                    if not text:
                        continue
                    
                    lines = text.split('\n')
                    i = 0
                    while i < len(lines):
                        line = lines[i].strip()
                        
                        # Scotia format: "DDMON DESCRIPTION J$ AMOUNT +/- [J$ BALANCE]"
                        # Match lines starting with DDMON (e.g., 10NOV, 08JAN, 24DEC)
                        tx_match = re.match(
                            r'^(\d{2})([A-Z]{3})\s+(.+?)\s+J\$\s+([\d,]+\.\d{2})\s*([+\-])',
                            line
                        )
                        
                        if tx_match:
                            day = int(tx_match.group(1))
                            month_str = tx_match.group(2)
                            description = tx_match.group(3).strip()
                            amount = float(tx_match.group(4).replace(',', ''))
                            direction = tx_match.group(5)
                            
                            # Parse the balance if present at end of line
                            balance = 0
                            balance_match = re.search(r'J\$\s+([\d,]+\.\d{2})\s*$', line)
                            if balance_match and direction in ['+', '-']:
                                # Check if the balance amount is different from the transaction amount
                                bal_amount = float(balance_match.group(1).replace(',', ''))
                                if bal_amount != amount:
                                    balance = bal_amount
                            
                            # Convert month abbreviation to number
                            month_map = {
                                'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4,
                                'MAY': 5, 'JUN': 6, 'JUL': 7, 'AUG': 8,
                                'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                            }
                            month_num = month_map.get(month_str, 1)
                            
                            # Determine year (handle statement spanning two years)
                            tx_year = statement_year
                            if month_num > 9 and statement_year > 2000:
                                # If month is Oct-Dec and statement ends in next year,
                                # the transaction is from the previous year
                                if year_match:
                                    start_month_str = year_match.group(1)[2:5]
                                    start_month = month_map.get(start_month_str, 1)
                                    if start_month >= 10 and month_num >= start_month:
                                        tx_year = statement_year - 1
                            
                            try:
                                tx_date = datetime(tx_year, month_num, day)
                            except ValueError:
                                i += 1
                                continue
                            
                            # Look ahead for description continuation (next line without a date)
                            if i + 1 < len(lines):
                                next_line = lines[i + 1].strip()
                                if next_line and not re.match(r'^\d{2}[A-Z]{3}\s', next_line):
                                    # Skip known non-transaction lines
                                    if not next_line.startswith('*') and not next_line.startswith('Page '):
                                        if 'SERVICE CHARGE' not in description and 'GCT' not in description:
                                            description += " | " + next_line
                            
                            # Skip service charges and GCT tax entries
                            if any(skip in description for skip in ['SERVICE CHARGE', 'GCT/GOVT TAX', 'GCT TAX']):
                                i += 1
                                continue
                            
                            credit = amount if direction == '+' else 0
                            debit = amount if direction == '-' else 0
                            
                            transactions.append({
                                "date": tx_date,
                                "description": description,
                                "debit": debit,
                                "credit": credit,
                                "balance": balance
                            })
                        
                        i += 1
        
        except Exception as e:
            print(f"  ✗ PDF parsing error: {e}")
        
        return transactions
    
    @staticmethod
    def parse_csv(file_path):
        """Parses a CSV bank statement."""
        if not os.path.exists(file_path):
            print(f"  ✗ File not found: {file_path}")
            return []
        
        transactions = []
        
        try:
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    # Normalize column names (case-insensitive)
                    normalized = {k.lower().strip(): v.strip() for k, v in row.items() if v}
                    
                    # Find date
                    date_str = (normalized.get('date') or normalized.get('transaction date') 
                                or normalized.get('post date') or normalized.get('value date') or "")
                    
                    # Find description
                    desc = (normalized.get('description') or normalized.get('details') 
                            or normalized.get('narrative') or normalized.get('particulars') or "")
                    
                    # Find amounts
                    debit = StatementParser._parse_amount(
                        normalized.get('debit') or normalized.get('withdrawal') 
                        or normalized.get('dr') or ""
                    )
                    credit = StatementParser._parse_amount(
                        normalized.get('credit') or normalized.get('deposit') 
                        or normalized.get('cr') or ""
                    )
                    
                    # Some CSVs have a single "amount" column (negative = debit)
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
            print(f"  ✗ CSV parsing error: {e}")
        
        return transactions
    
    @staticmethod
    def _parse_row(cells):
        """Tries to parse a table row as a transaction."""
        # Look for a cell that contains a date
        date_val = None
        desc_val = ""
        debit_val = 0
        credit_val = 0
        
        for cell in cells:
            if not cell:
                continue
            
            # Try to find a date
            if not date_val:
                parsed = StatementParser._parse_date(cell)
                if parsed:
                    date_val = parsed
                    continue
            
            # Try to find amounts (numeric values)
            amount = StatementParser._parse_amount(cell)
            if amount > 0 and not desc_val:
                # Could be an amount, but if we haven't found a description yet,
                # this might be the description (e.g., a reference number)
                if len(cell) > 10 and not cell.replace(',', '').replace('.', '').isdigit():
                    desc_val = cell
                elif debit_val == 0:
                    debit_val = amount
                else:
                    credit_val = amount
            elif len(cell) > 3 and not desc_val:
                desc_val = cell
        
        if date_val and (debit_val > 0 or credit_val > 0):
            return {
                "date": date_val,
                "description": desc_val,
                "debit": debit_val,
                "credit": credit_val,
                "balance": 0
            }
        return None
    
    @staticmethod
    def _parse_text_line(line):
        """Tries to parse a text line as a transaction."""
        # Common pattern: DATE    DESCRIPTION    AMOUNT
        date_patterns = [
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(\d{1,2}\s+\w{3}\s+\d{2,4})',
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, line)
            if match:
                date_str = match.group(1)
                parsed_date = StatementParser._parse_date(date_str)
                if parsed_date:
                    # Find amounts in the rest of the line
                    amounts = re.findall(r'[\d,]+\.\d{2}', line)
                    if amounts:
                        desc = line[match.end():].strip()
                        # Remove amounts from description  
                        for amt in amounts:
                            desc = desc.replace(amt, '').strip()
                        desc = re.sub(r'\s+', ' ', desc).strip()
                        
                        return {
                            "date": parsed_date,
                            "description": desc,
                            "debit": float(amounts[0].replace(',', '')) if len(amounts) >= 1 else 0,
                            "credit": float(amounts[1].replace(',', '')) if len(amounts) >= 2 else 0,
                            "balance": float(amounts[-1].replace(',', '')) if len(amounts) >= 3 else 0
                        }
        return None
    
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
        
        # Remove currency symbols and spaces
        cleaned = re.sub(r'[^0-9.,\-]', '', str(amount_str))
        cleaned = cleaned.replace(',', '')
        
        try:
            return abs(float(cleaned))
        except ValueError:
            return 0

# ==========================================
# 2. RULE-BASED TRANSACTION CLASSIFIER
# ==========================================

class RuleBasedClassifier:
    """
    Classifies bank transactions using keyword matching.
    No AI required — pure pattern recognition.
    """
    
    # Known subscription services (matched against transaction description)
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
    
    # Transaction type patterns (from Scotia Bank format)
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
# 3. PATTERN DETECTOR
# ==========================================

class PatternDetector:
    """
    Analyzes classified transactions across multiple statements 
    to auto-detect:
    - Salary: day, amount, frequency
    - Subscriptions: name, amount, renewal day, failure rate
    - Recurring expenses: name, amount, day
    """
    
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
# 4. SALARY CYCLE TRACKER
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
            return "SAFE ZONE", "🟢"
        elif position <= 0.6:
            return "MID-CYCLE", "🟡"
        elif position <= 0.8:
            return "CAUTION ZONE", "🟠"
        else:
            return "DANGER ZONE", "🔴"

# ==========================================
# 5. EXPENSE PROFILER
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
# 6. RISK SCORE ENGINE
# ==========================================

class RiskScoreEngine:
    """
    Combines 4 signals into a Risk Score (0.0 to 1.0):
    
    Risk = w₁ × PaycycleFactor + w₂ × ClusterPenalty 
         + w₃ × HistoricalFailRate + w₄ × ExpenseLoadFactor
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
            risk_label, risk_icon = "LOW", "🟢"
            advice = "Your renewal should go through fine."
        elif risk_score <= 0.55:
            risk_label, risk_icon = "MODERATE", "🟡"
            advice = "Check your balance a day before renewal."
        elif risk_score <= 0.75:
            risk_label, risk_icon = "HIGH", "🟠"
            advice = "⚠ High risk of insufficient funds. Transfer money to your card."
        else:
            risk_label, risk_icon = "CRITICAL", "🔴"
            advice = "🚨 This renewal will likely fail. Add funds immediately."
        
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
# 7. PAYCYCLE VISUALIZER
# ==========================================

def draw_paycycle_bar(salary_tracker, subscriptions):
    """Draws a visual 30-day bar showing payday, zones, and renewal positions."""
    pay_day = salary_tracker.pay_day
    
    print(f"\n  ┌─ 30-DAY PAYCYCLE MAP (Payday: Day {pay_day}) ─────────┐")
    
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
            zone_bar += "💰"
        elif char != " ":
            zone_bar += f"[{char}]"
        else:
            if pos <= 0.3:
                zone_bar += "█"
            elif pos <= 0.6:
                zone_bar += "▓"
            elif pos <= 0.8:
                zone_bar += "▒"
            else:
                zone_bar += "░"
    
    print(f"  │ {zone_bar}")
    print(f"  │ █ Safe  ▓ Mid  ▒ Caution  ░ Danger  💰 Payday")
    
    for marker, name in sub_markers.items():
        print(f"  │ [{marker}] = {name}")
    
    print(f"  └{'─' * 48}┘")

# ==========================================
# 8. INTERACTIVE CLI
# ==========================================

def run_app():
    print("=========================================")
    print("  RenewalSense — Smart Renewal Alerts    ")
    print("=========================================")
    run_statement_mode()

def run_statement_mode():
    """Statement upload mode — parses PDFs/CSVs and auto-detects everything."""
    
    # Initialize rule-based classifier (no AI needed)
    classifier = RuleBasedClassifier()
    print("  ✓ Rule-based classifier ready (no AI required)")
    
    # --- Collect Statement Files via Windows File Picker ---
    print("\n[Step 1: Select your bank statements]")
    print("  A file picker will open — select 1-4 PDF or CSV bank statements.\n")
    
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
        print("  ✗ No files selected.")
        return
    
    # Limit to 4 files
    file_paths = file_paths[:4]
    
    all_transactions = []
    file_count = 0
    
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"  ✗ File not found: {file_path}")
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
            print(f"  ✗ Unsupported format: {ext}. Use PDF or CSV.")
            continue
        
        if txs:
            all_transactions.extend(txs)
            file_count += 1
            print(f"  ✓ Parsed {len(txs)} transactions from {file_name}")
        else:
            print(f"  ✗ No transactions found in {file_name}.")
    
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
    
    print("  ✓ Classification complete:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat.replace('_', ' ').title():20s} {count} transactions")
    
    # --- Auto-detect Patterns ---
    print(f"\n[Step 3: Detecting financial patterns...]")
    
    # Detect salary
    salary_info = PatternDetector.detect_salary(classified)
    if salary_info:
        print(f"  ✓ Salary detected: ${salary_info['amount']:,.2f} on day {salary_info['pay_day']} ({salary_info['frequency']})")
        salary_tracker = SalaryCycleTracker(
            salary_info['amount'], salary_info['pay_day'], salary_info['frequency']
        )
    else:
        print("  ✗ Could not auto-detect salary. Please enter manually:")
        salary_amount = float(input("    Monthly salary: $"))
        pay_day = int(input("    Payday (day of month): "))
        salary_tracker = SalaryCycleTracker(salary_amount, pay_day)
    
    # Detect subscriptions  
    subs = PatternDetector.detect_subscriptions(classified)
    if subs:
        print(f"\n  ✓ Detected {len(subs)} subscription(s):")
        for s in subs:
            fail_str = f" ({s['past_failures']} failed)" if s['past_failures'] > 0 else ""
            print(f"    • {s['name']} — ${s['amount']:.2f}/mo on day {s['renewal_day']}{fail_str}")
    else:
        print("  ✗ No subscriptions auto-detected.")
        return
    
    # Detect expenses
    expenses = PatternDetector.detect_expenses(classified)
    expense_profiler = ExpenseProfiler()
    if expenses:
        print(f"\n  ✓ Detected {len(expenses)} recurring expense(s):")
        for e in expenses:
            expense_profiler.add_expense(e['name'], e['amount'], e['day'])
            print(f"    • {e['name']} — ${e['amount']:,.2f} on day {e['day']}")
    else:
        print("  ℹ No major recurring expenses detected.")
    
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
        print(f"    Clustering:  ${bd['cluster_amount']:.2f} in expenses within ±3 days ({bd['cluster_factor']:.0%})")
        print(f"    Load:        {bd['load_factor']:.0%} of salary consumed by day {res['renewal_day']}")
        print(f"    History:     {bd['fail_rate']:.0%} failure rate")
        
        if res['risk_label'] in ['HIGH', 'CRITICAL']:
            high_risk_count += 1
            print(f"\n  ⚡ ALERT: {res['advice']}")
        else:
            print(f"\n  ℹ  {res['advice']}")
        
        print(f"  {'─' * 40}")
    
    # --- Summary ---
    total_expenses = expense_profiler.total_monthly_expenses()
    total_sub_cost = sum(r["amount"] for r in results)
    
    print(f"\n  ═══════════════════════════════════════")
    print(f"  SUMMARY")
    print(f"  ═══════════════════════════════════════")
    print(f"  Total subscriptions:   {len(results)}")
    print(f"  High-risk renewals:    {high_risk_count}")
    print(f"  Total sub spending:    ${total_sub_cost:,.2f}/mo")
    print(f"  Income remaining:      ${salary_tracker.salary_amount - total_expenses - total_sub_cost:,.2f}/mo (after expenses + subs)")
    
    if high_risk_count > 0:
        print(f"\n  🚨 You have {high_risk_count} high-risk renewal(s).")
        print(f"  Set reminders to check your balance the day before.")
    else:
        print(f"\n  ✅ All renewals are in a safe zone. You're good!")
    
    print()

if __name__ == "__main__":
    run_app()
