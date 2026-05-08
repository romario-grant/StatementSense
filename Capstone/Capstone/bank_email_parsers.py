import re


# ---------------------- NCB Email Parser ---------------------- #
# Handles: Transaction Approved (purchase), Withdrawal Approved, Withdrawal Declined
# Date is explicit in the email body: DD/MMM/YYYY
# Amount format: JMD X,XXX.XX

def parse_ncb_email(email_body):
    """
    Parses NCB Jamaica transaction notification emails.
    Returns a dict or None if no match.
    """

    # Determine transaction type
    is_declined = bool(re.search(r"declined", email_body, re.IGNORECASE))
    is_reversed = bool(re.search(r"reversed", email_body, re.IGNORECASE))
    is_withdrawal = bool(re.search(r"withdrawal", email_body, re.IGNORECASE)) or bool(
        re.search(r"Merchant\s+COMMERCIAL", email_body, re.IGNORECASE)
    )

    # Extract structured fields from the table body
    def extract_field(label, text):
        pattern = re.compile(rf"{label}\s+(.+?)(?:\n|$)", re.IGNORECASE)
        match = pattern.search(text)
        return match.group(1).strip() if match else None

    reference   = extract_field("Reference Number", email_body)
    card_ending = extract_field("Card Number Ending", email_body)
    card_type   = extract_field("Card Type", email_body)
    date_raw    = extract_field("Date", email_body)
    time_raw    = extract_field("Time", email_body)
    merchant    = extract_field("Merchant", email_body)
    status      = extract_field("Status", email_body)
    reason      = extract_field("Reason", email_body)  # Only present on declined

    # Amount: "JMD 1,000.00" or "JMD 508.31" or "JMD997.27" (no space variant)
    amount_match = re.search(r"Amount\s+JMD\s*([\d,]+\.\d{2})", email_body, re.IGNORECASE)
    amount = float(amount_match.group(1).replace(",", "")) if amount_match else None

    # Normalise date from DD/MMM/YYYY → YYYY-MM-DD
    date_normalised = None
    if date_raw:
        try:
            from datetime import datetime
            date_normalised = datetime.strptime(date_raw.strip(), "%d/%b/%Y").strftime("%Y-%m-%d")
        except ValueError:
            date_normalised = date_raw.strip()

    if amount is None:
        return None

    transaction_type = "Withdrawal" if is_withdrawal else "Purchase"
    if is_declined:
        transaction_type += " (Declined)"
    elif is_reversed:
        transaction_type += " (Reversed)"

    return {
        "bank": "NCB",
        "type": transaction_type,
        "amount": amount,
        "currency": "JMD",
        "merchant": merchant,
        "date": date_normalised,
        "time": time_raw,
        "status": status or ("DECLINED" if is_declined else "APPROVED"),
        "card_ending": card_ending,
        "card_type": card_type,
        "reference": reference,
        "decline_reason": reason,  # None unless declined
    }


# ---------------------- Scotiabank Email Parser ---------------------- #
# Handles: Purchase (local), Purchase (international), Transfer out,
#          ATM withdrawal, Deposit/Transfer in
# NOTE: Scotia emails do NOT include a date — use internalDate from Gmail API

def parse_scotiabank_email(email_body):
    """
    Parses Scotiabank Jamaica transaction notification emails.
    Returns a dict or None if no match.
    Scotia emails carry no explicit date — caller should inject `date` from
    the Gmail message's internalDate timestamp.
    """
    # Collapse mid-sentence line breaks so regex matches across wrapped lines
    email_body = re.sub(r'\n(?!\n)', ' ', email_body)

    # --- Purchase (outside country) ---
    # "There was a purchase outside of the country for $553.95 at UBER * PENDING
    #  on your Scotiabank Debit Card at 09:25 am EST."
    m = re.search(
        r"purchase outside of the country for \$([\d,]+\.\d{2}) at (.+?) on your\s+Scotiabank",
        email_body, re.IGNORECASE | re.DOTALL
    )
    if m:
        return {
            "bank": "Scotiabank",
            "type": "Purchase (International)",
            "amount": float(m.group(1).replace(",", "")),
            "currency": "JMD",
            "merchant": re.sub(r"\s+", " ", m.group(2)).strip(),
            "status": "APPROVED",
            "time": _extract_scotia_time(email_body),
            "account_ending": _extract_scotia_account(email_body),
        }

    # --- Purchase (local) ---
    # "There was a purchase for $7,935.00 at VICTORY APPAREL GROUP
    #  on your Scotiabank Debit Card at 01:30 pm EST."
    m = re.search(
        r"There was a purchase for \$([\d,]+\.\d{2}) at (.+?) on your\s+Scotiabank",
        email_body, re.IGNORECASE | re.DOTALL
    )
    if m:
        return {
            "bank": "Scotiabank",
            "type": "Purchase",
            "amount": float(m.group(1).replace(",", "")),
            "currency": "JMD",
            "merchant": re.sub(r"\s+", " ", m.group(2)).strip(),
            "status": "APPROVED",
            "time": _extract_scotia_time(email_body),
            "account_ending": _extract_scotia_account(email_body),
        }

    # --- Transfer out ---
    # "A transfer was made for $4,000.00 from account ***3640 at 09:41 am EST."
    m = re.search(
        r"transfer was made for \$([\d,]+\.\d{2}) from account (\*+\d+) at ([\d:]+ [apm]+ \w+)",
        email_body, re.IGNORECASE
    )
    if m:
        return {
            "bank": "Scotiabank",
            "type": "Transfer (Out)",
            "amount": float(m.group(1).replace(",", "")),
            "currency": "JMD",
            "merchant": None,
            "status": "APPROVED",
            "time": m.group(3).strip(),
            "account_ending": m.group(2).strip(),
        }

    # --- ATM Withdrawal ---
    # "Your Scotiabank Debit Card was used for an ATM cash withdrawal
    #  on account ***3640 for $5,000.00 at 03:51 pm EST."
    m = re.search(
        r"ATM cash withdrawal on account (\*+\d+) for \$([\d,]+\.\d{2}) at ([\d:]+ [apm]+ \w+)",
        email_body, re.IGNORECASE
    )
    if m:
        return {
            "bank": "Scotiabank",
            "type": "ATM Withdrawal",
            "amount": float(m.group(2).replace(",", "")),
            "currency": "JMD",
            "merchant": None,
            "status": "APPROVED",
            "time": m.group(3).strip(),
            "account_ending": m.group(1).strip(),
        }

    # --- Deposit / Transfer in ---
    # "You have received a transfer or deposit to your account ending in ***3640
    #  for $51,200.00 JMD."
    m = re.search(
        r"received a transfer or deposit to your account ending in (\*+\d+) for \$([\d,]+\.\d{2})",
        email_body, re.IGNORECASE
    )
    if m:
        return {
            "bank": "Scotiabank",
            "type": "Deposit",
            "amount": float(m.group(2).replace(",", "")),
            "currency": "JMD",
            "merchant": None,
            "status": "APPROVED",
            "time": None,
            "account_ending": m.group(1).strip(),
        }

    return None


# ---------------------- Scotiabank Helpers ---------------------- #

def _extract_scotia_time(text):
    """Pulls time string like '09:25 am EST' from Scotia email body."""
    m = re.search(r"at ([\d:]+ [apm]+ \w+)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _extract_scotia_account(text):
    """Pulls masked account number like ***3640 from Scotia email body."""
    m = re.search(r"account \*+(\d+)", text, re.IGNORECASE)
    return f"***{m.group(1)}" if m else None


# ---------------------- Unified Parser ---------------------- #

def parse_bank_email(email_body, source_bank):
    """
    Single entry point. Pass the plain-text email body and the bank identifier.
    Returns a normalised transaction dict or None.

    source_bank: "NCB" | "Scotiabank" | "CIBC"
    """
    if source_bank == "NCB":
        return parse_ncb_email(email_body)
    elif source_bank == "Scotiabank":
        return parse_scotiabank_email(email_body)
    else:
        return None  # CIBC handled by existing parse_cibc_email()


# ---------------------- Quick smoke test ---------------------- #

if __name__ == "__main__":
    ncb_sample = """
    Hello JADA,
    Thank you for choosing your NCB card as your payment method of choice.

    Reference Number    753475453
    Card Number Ending  8194
    Card Type           VISA DEBIT CLASSIC
    Date                22/MAR/2026
    Time                05:26 PM
    Amount              JMD 508.31
    Merchant            UBER * PENDING
    Status              APPROVED
    """

    scotia_intl = "There was a purchase outside of the country for $553.95 at UBER * PENDING on your\nScotiabank Debit Card at 09:25 am EST."
    scotia_local = "There was a purchase for $7,935.00 at VICTORY APPAREL GROUP on your\nScotiabank Debit Card at 01:30 pm EST."
    scotia_transfer_out = "A transfer was made for $4,000.00 from account ***3640 at 09:41 am EST."
    scotia_atm = "Your Scotiabank Debit Card was used for an ATM cash withdrawal on account ***3640 for $5,000.00 at 03:51 pm EST."
    scotia_deposit = "You have received a transfer or deposit to your account ending in ***3640 for $51,200.00 JMD."

    print("NCB purchase:      ", parse_ncb_email(ncb_sample))
    print("Scotia intl:       ", parse_scotiabank_email(scotia_intl))
    print("Scotia local:      ", parse_scotiabank_email(scotia_local))
    print("Scotia transfer:   ", parse_scotiabank_email(scotia_transfer_out))
    print("Scotia ATM:        ", parse_scotiabank_email(scotia_atm))
    print("Scotia deposit:    ", parse_scotiabank_email(scotia_deposit))