from datetime import datetime
import unittest

from backend.app.engines.subscription_engine import (
    _classify_transactions,
    _detect_price_changes,
    _detect_trials,
    _run_subscription_detection,
)


def _tx(date, description, amount):
    return {
        "date": datetime.strptime(date, "%Y-%m-%d"),
        "description": description,
        "debit": abs(amount) if amount < 0 else 0,
        "credit": amount if amount > 0 else 0,
        "balance": 0,
        "currency": "JMD",
        "amount": amount,
    }


def january_statement_pattern():
    return _classify_transactions([
        _tx("2025-11-10", "ITB-CUSTOMER TRAN DR Transfer to ROMARIO GRANT 7107", -1000.00),
        _tx("2025-11-17", "ITB-CUSTOMER TRAN DR Transfer to ROMARIO GRANT 7107", -1000.00),
        _tx("2026-01-02", "THIRD PARTY TRF BNS Transfer to TASHALEE GRANT 8547", -1000.00),
        _tx("2026-01-02", "THIRD PARTY TRF BNS Transfer to TASHALEE GRANT 8547", -54000.00),
        _tx("2025-12-19", "POS PURCHASE UBER *TRIP HELP.UBER.C Vorden NL", -867.78),
        _tx("2026-01-16", "POS PURCHASE UBER *TRIP HELP.UBER.C Vorden NL", -1078.59),
        _tx("2026-01-26", "POS PURCHASE UBER *TRIP HELP.UBER.C Vorden NL", -429.76),
        _tx("2025-12-29", "POS PURCHASE Google YouTubePremium Mountain ViewUS", -803.20),
        _tx("2025-12-29", "SERVICE CHARGE Google YouTubePremium Mountain ViewUS For 29DEC25", -11.52),
        _tx("2026-01-08", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -559.85),
        _tx("2026-01-08", "SERVICE CHARGE SPOTIFY AB STOCKHOLM SE For 08JAN26", -11.52),
        _tx("2026-01-27", "POS PURCHASE Google YouTubePremium Mountain ViewUS", -802.44),
        _tx("2026-01-27", "SERVICE CHARGE Google YouTubePremium Mountain ViewUS For 27JAN26", -11.52),
    ])


class SubscriptionEngineRegressionTests(unittest.TestCase):
    def setUp(self):
        self.transactions = january_statement_pattern()

    def test_transfers_do_not_become_subscriptions(self):
        subscriptions, renewals = _run_subscription_detection(self.transactions)

        self.assertEqual([sub["merchant"] for sub in subscriptions], ["YouTube"])
        self.assertEqual(subscriptions[0]["period"], "monthly")
        self.assertAlmostEqual(subscriptions[0]["amount"], 802.82)
        self.assertEqual(renewals, [])

    def test_transfer_pattern_does_not_create_trial_alert(self):
        self.assertEqual(_detect_trials(self.transactions), [])

    def test_variable_spend_and_tiny_changes_do_not_create_price_alerts(self):
        self.assertEqual(_detect_price_changes(self.transactions), [])

    def test_service_charge_rows_are_not_subscription_rows(self):
        service_charge_rows = [
            tx for tx in self.transactions
            if tx["description"].lower().startswith("service charge")
        ]

        self.assertTrue(service_charge_rows)
        self.assertTrue(all(tx["category"] == "other" for tx in service_charge_rows))
        self.assertTrue(all(tx["excluded_from_subscription_analysis"] for tx in service_charge_rows))


if __name__ == "__main__":
    unittest.main()
