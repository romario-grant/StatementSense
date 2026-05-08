"""
Unit tests for bank_email_parsers.py
Run with: pytest test_bank_email_parsers.py -v
"""

import pytest
from bank_email_parsers import parse_ncb_email, parse_scotiabank_email, parse_bank_email


# ================================================================
# NCB TESTS
# ================================================================

class TestNCBParser:

    def test_purchase_approved(self):
        body = """
        Hello JADA,
        Reference Number    753475453
        Card Number Ending  8194
        Card Type           VISA DEBIT CLASSIC
        Date                22/MAR/2026
        Time                05:26 PM
        Amount              JMD 508.31
        Merchant            UBER * PENDING
        Status              APPROVED
        """
        result = parse_ncb_email(body)
        assert result is not None
        assert result["bank"] == "NCB"
        assert result["type"] == "Purchase"
        assert result["amount"] == 508.31
        assert result["currency"] == "JMD"
        assert result["merchant"] == "UBER * PENDING"
        assert result["date"] == "2026-03-22"
        assert result["status"] == "APPROVED"
        assert result["card_ending"] == "8194"
        assert result["reference"] == "753475453"
        assert result["decline_reason"] is None

    def test_withdrawal_approved(self):
        body = """
        Hello KYE,
        Reference Number    743271301
        Card Number Ending  4719
        Card Type           VISA DEBIT CLASSIC
        Date                26/FEB/2026
        Time                05:29 PM
        Amount              JMD 1,000.00
        Merchant            COMMERCIAL
        Status              APPROVED
        """
        result = parse_ncb_email(body)
        assert result is not None
        assert result["type"] == "Withdrawal"
        assert result["amount"] == 1000.00
        assert result["merchant"] == "COMMERCIAL"
        assert result["date"] == "2026-02-26"
        assert result["status"] == "APPROVED"

    def test_withdrawal_declined(self):
        body = """
        Hello JADA,
        Reference Number    751842470
        Card Number Ending  8194
        Card Type           VISA DEBIT CLASSIC
        Date                18/MAR/2026
        Time                05:28 PM
        Amount              JMD 1,000.00
        Merchant            COMMERCIAL
        Status              DECLINED
        Reason              The selected checking account type (From) is not linked to the card
        """
        result = parse_ncb_email(body)
        assert result is not None
        assert result["type"] == "Withdrawal (Declined)"
        assert result["amount"] == 1000.00
        assert result["status"] == "DECLINED"
        assert result["decline_reason"] is not None

    def test_large_amount_with_comma(self):
        body = """
        Date                01/JAN/2026
        Amount              JMD 15,750.00
        Merchant            NETFLIX
        Status              APPROVED
        """
        result = parse_ncb_email(body)
        assert result is not None
        assert result["amount"] == 15750.00

    def test_returns_none_if_no_amount(self):
        body = "Hello, this is a generic NCB email with no transaction details."
        result = parse_ncb_email(body)
        assert result is None

    def test_transaction_reversed(self):
        body = """
        Hello JADA,
        Your transaction was successfully reversed. See details below:
        Reference Number    754075911
        Card Number Ending  8194
        Card Type           VISA DEBIT CLASSIC
        Date                24/MAR/2026
        Time                09:02 AM
        Amount              JMD997.27
        Merchant            UBER * PENDING
        Status              REVERSED
        """
        result = parse_ncb_email(body)
        assert result is not None
        assert result["type"] == "Purchase (Reversed)"
        assert result["amount"] == 997.27
        assert result["date"] == "2026-03-24"
        assert result["merchant"] == "UBER * PENDING"

    def test_amount_no_space(self):
        # JMD997.27 — no space between JMD and number
        body = """
        Date                24/MAR/2026
        Amount              JMD997.27
        Merchant            UBER * PENDING
        Status              REVERSED
        """
        result = parse_ncb_email(body)
        assert result is not None
        assert result["amount"] == 997.27
        body = """
        Date                15/JUN/2025
        Amount              JMD 200.00
        Merchant            SPOTIFY
        Status              APPROVED
        """
        result = parse_ncb_email(body)
        assert result["date"] == "2025-06-15"


# ================================================================
# SCOTIABANK TESTS
# ================================================================

class TestScotiabankParser:

    def test_purchase_international(self):
        # Realistic Gmail body — newline mid-sentence
        body = "There was a purchase outside of the country for $553.95 at UBER * PENDING on your\nScotiabank Debit Card at 09:25 am EST."
        result = parse_scotiabank_email(body)
        assert result is not None
        assert result["bank"] == "Scotiabank"
        assert result["type"] == "Purchase (International)"
        assert result["amount"] == 553.95
        assert result["merchant"] == "UBER * PENDING"
        assert result["time"] == "09:25 am EST"
        assert result["status"] == "APPROVED"

    def test_purchase_local(self):
        body = "There was a purchase for $7,935.00 at VICTORY APPAREL GROUP on your\nScotiabank Debit Card at 01:30 pm EST."
        result = parse_scotiabank_email(body)
        assert result is not None
        assert result["type"] == "Purchase"
        assert result["amount"] == 7935.00
        assert result["merchant"] == "VICTORY APPAREL GROUP"
        assert result["time"] == "01:30 pm EST"

    def test_transfer_out(self):
        body = "A transfer was made for $4,000.00 from account ***3640 at 09:41 am EST."
        result = parse_scotiabank_email(body)
        assert result is not None
        assert result["type"] == "Transfer (Out)"
        assert result["amount"] == 4000.00
        assert result["account_ending"] == "***3640"
        assert result["merchant"] is None

    def test_atm_withdrawal(self):
        body = "Your Scotiabank Debit Card was used for an ATM cash withdrawal on account ***3640 for $5,000.00 at 03:51 pm EST."
        result = parse_scotiabank_email(body)
        assert result is not None
        assert result["type"] == "ATM Withdrawal"
        assert result["amount"] == 5000.00
        assert result["account_ending"] == "***3640"
        assert result["time"] == "03:51 pm EST"

    def test_deposit(self):
        body = "You have received a transfer or deposit to your account ending in ***3640 for $51,200.00 JMD."
        result = parse_scotiabank_email(body)
        assert result is not None
        assert result["type"] == "Deposit"
        assert result["amount"] == 51200.00
        assert result["account_ending"] == "***3640"
        assert result["merchant"] is None

    def test_large_amount_with_comma(self):
        body = "There was a purchase for $12,500.00 at COURTS JAMAICA on your\nScotiabank Debit Card at 11:00 am EST."
        result = parse_scotiabank_email(body)
        assert result is not None
        assert result["amount"] == 12500.00

    def test_returns_none_for_unrecognised_body(self):
        body = "Hi JADA, your password has been changed successfully."
        result = parse_scotiabank_email(body)
        assert result is None

    def test_merchant_whitespace_normalised(self):
        # Merchant name spanning a line break should collapse to single space
        body = "There was a purchase outside of the country for $99.99 at ADOBE\nSYSTEMS on your\nScotiabank Debit Card at 02:00 pm EST."
        result = parse_scotiabank_email(body)
        assert result is not None
        assert "\n" not in result["merchant"]
        assert "  " not in result["merchant"]


# ================================================================
# UNIFIED ENTRY POINT TESTS
# ================================================================

class TestUnifiedParser:

    def test_routes_ncb(self):
        body = """
        Date                22/MAR/2026
        Amount              JMD 508.31
        Merchant            SPOTIFY
        Status              APPROVED
        """
        result = parse_bank_email(body, "NCB")
        assert result is not None
        assert result["bank"] == "NCB"

    def test_routes_scotiabank(self):
        body = "There was a purchase for $500.00 at NETFLIX on your\nScotiabank Debit Card at 10:00 am EST."
        result = parse_bank_email(body, "Scotiabank")
        assert result is not None
        assert result["bank"] == "Scotiabank"

    def test_cibc_returns_none(self):
        # CIBC handled by existing parse_cibc_email — unified router returns None
        result = parse_bank_email("some cibc body", "CIBC")
        assert result is None

    def test_unknown_bank_returns_none(self):
        result = parse_bank_email("some body", "JN Bank")
        assert result is None