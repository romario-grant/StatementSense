import sys
import csv
import math
from datetime import date, datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional
from statistics import mean, stdev


class Transaction:
    def __init__(self, date, amount, merchant):
        self.date = date
        self.amount = amount
        self.merchant = merchant

    def __str__(self):
        return f"{self.date}\n{self.amount}\n{self.merchant}"
        

class Subscription:
    def __init__(self, merchant, transactions,period, period_days,confidence,avg_amt):
        self.merchant= merchant
        self.transactions= transactions
        self.period= period                 # "weekly" | "bi-weekly" | "monthly" | "yearly" | "irregular"
        self.period_days= period_days       # average gap in days
        self.confidence= confidence         # 0-1
        self.avg_amount = avg_amt
    def __str__(self):
        return f"{self.merchant}\n{self.transactions}\n{self.period}\n{self.period_days}\n{self.confidence}"

    def next_expected(self):
        if self.period_days is None or not self.transactions:
            return None
        last = max(t.date for t in self.transactions)
        return last + timedelta(round(self.period_days))

def detect_subscriptions(
    transactions: list[Transaction],
    min_occurrences: int = 2,
    amount_tolerance: float = 0.05,
):
    merchant_list = defaultdict(list)
    subscriptions = []
    for trans in transactions:
        merchant_list[trans.merchant.strip().lower()].append(trans)

    for merch,trans in merchant_list.items():
        if len(trans) < min_occurrences:
            continue
        trans_sorted = sorted(trans, key=lambda t: t.date)
        amounts = [t.amount for t in trans_sorted]
        avg_amt = mean(amounts)
        amount_limit = all(abs(a - avg_amt) / avg_amt <= amount_tolerance for a in amounts)
        if not amount_limit:
            continue
        day_gap = []
        for i in range(1,len(trans_sorted)):
            delta = (trans_sorted[i].date - trans_sorted[i - 1].date).days
            day_gap.append(float(delta))
        print(merch,day_gap)

        period, confidence  = detect_period(day_gap)
        print(period,confidence)

        if confidence < 0.4:
            continue

        sub = Subscription(
            merchant=trans_sorted[0].merchant,   
            transactions=trans_sorted,
            period=period,
            period_days=round(mean(day_gap), 1) if day_gap else None,
            confidence=confidence,
            avg_amt= avg_amt,
        )

        subscriptions.append(sub)

    return subscriptions

period_window  = {
    "weekly":   (5,   9),
    "biweekly": (12,  16),
    "monthly":  (25,  35),
    "quarterly":(80,  100),
    "yearly":   (340, 390),
}

def detect_period(gaps):
    if gaps == []:
        return None, 0.0
    
    avg = mean(gaps)
    spread = stdev(gaps) if len(gaps) > 1 else 0.0

    for label,(lower_range,upper_range) in period_window.items():
        if lower_range <= avg <= upper_range:
            if spread > 0:
                coeff_var = spread*10/avg
                confidence = math.exp((-1)*coeff_var/3)
                return label,round(confidence,2)
            return label,1.0
    return None,0.0

def print_report(subscriptions):
    if not subscriptions:
        print("No subscriptions detected.")
        return


    print(f"{len(subscriptions)} subscription(s) found")
 

    for sub in subscriptions:
        print(f"  Merchant   : {sub.merchant}")
        print(f"  period     : {sub.period}  (~{sub.period_days} days)")
        print(f"  Confidence : {sub.confidence:.0%}")
        print(f"  Amount     : ${sub.avg_amount:.2f}/charge")
        print(f"  Charges    : {len(sub.transactions)}")
        if sub.next_expected():
            print(f"  Next due   : {sub.next_expected()}")
        print()

    print()
#------CSV LOADER------------------------------------------------------

def load_csv_path(path_str):

    date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"]

    def parse_date(s):
        for fmt in date_formats:
            try:
                return datetime.strptime(s.strip(), fmt).date()
            except ValueError:
                pass
        raise ValueError(f"Unrecognised date format: {s!r}")
    
    transactions = []
    with open(path_str, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        headers = {h.strip().lower() for h in reader.fieldnames or []}
        required = {"date", "amount", "merchant"}
        if not required.issubset(headers):
            raise ValueError(f"CSV must have columns: {required}. Found: {headers}")

        for row in reader:
            norm = {k.strip().lower(): v.strip() for k, v in row.items()}
            
            transactions.append(Transaction(
                date=parse_date(norm["date"]),
                amount=float(norm["amount"].replace("$", "").replace(",", "")),
                merchant=norm["merchant"],
            ))

    return transactions

def main() -> None:
    if len(sys.argv) > 1:
        path = sys.argv[1]
        try:
            rows = load_csv_path(path)
            print(f"{len(rows)} rows loaded.")
        except (FileNotFoundError, ValueError) as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("No CSV file provided")


    subs = detect_subscriptions(rows, min_occurrences=2)
    print_report(subs)


if __name__ == "__main__":
    main()
