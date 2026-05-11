from datetime import datetime
import unittest

from backend.app.engines.subscription_engine import (
    analyze_extracted_subscriptions,
    _classify_transactions,
    _detect_price_changes,
    _detect_trials,
    _dedupe_raw_transactions,
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
        self.assertAlmostEqual(subscriptions[0]["confidence"], 0.8)
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

    def test_single_charge_subscription_merchant_is_possible(self):
        result = analyze_extracted_subscriptions([
            {
                "bank": "Scotiabank",
                "date": "2026-01-08",
                "description": "POS PURCHASE SPOTIFY AB STOCKHOLM SE",
                "amount": -559.85,
                "balance": None,
                "currency": "JMD",
            }
        ])

        self.assertEqual(result["subscriptions"], [])
        self.assertEqual(result["possible_subscriptions"][0]["merchant"], "Spotify")
        self.assertEqual(result["summary"]["total_possible_subscriptions"], 1)

    def test_known_keyword_is_a_hint_not_subscription_category(self):
        classified = _classify_transactions([
            _tx("2026-01-08", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -559.85),
        ])

        self.assertEqual(classified[0]["category"], "merchant")
        self.assertTrue(classified[0]["known_subscription_hint"])
        self.assertEqual(classified[0]["vendor_name"], "Spotify")

    def test_subscription_language_without_known_brand_can_confirm_with_cadence(self):
        txns = _classify_transactions([
            _tx("2026-01-24", "CLAUDE.AI SUBSCRIPTION, SAN FRANCISCO (20.00 USD)", -3234.36),
            _tx("2026-02-24", "CLAUDE.AI SUBSCRIPTION, SAN FRANCISCO (20.00 USD)", -3212.61),
        ])

        subscriptions, _ = _run_subscription_detection(txns)

        self.assertEqual(len(subscriptions), 1)
        self.assertEqual(subscriptions[0]["merchant"], "Claude Ai Subscription")
        self.assertEqual(subscriptions[0]["period"], "monthly")
        self.assertFalse(subscriptions[0]["needs_review"])

    def test_known_keyword_without_cadence_is_not_confirmed(self):
        txns = _classify_transactions([
            _tx("2026-01-08", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -559.85),
            _tx("2026-01-11", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -559.85),
            _tx("2026-01-29", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -559.85),
        ])

        subscriptions, renewals = _run_subscription_detection(txns)

        self.assertEqual(subscriptions, [])
        self.assertEqual(renewals, [])

    def test_standing_order_recurring_payment_stays_possible_not_confirmed(self):
        result = analyze_extracted_subscriptions([
            {
                "bank": "Scotiabank",
                "date": "2026-01-28",
                "description": "CARD CHARGE STANDING ORDER -****6700",
                "amount": -24000.00,
                "balance": None,
                "currency": "JMD",
            },
            {
                "bank": "Scotiabank",
                "date": "2026-02-28",
                "description": "CARD CHARGE STANDING ORDER -****6700",
                "amount": -24000.00,
                "balance": None,
                "currency": "JMD",
            },
            {
                "bank": "Scotiabank",
                "date": "2026-03-28",
                "description": "CARD CHARGE STANDING ORDER -****6700",
                "amount": -24000.00,
                "balance": None,
                "currency": "JMD",
            },
        ])

        self.assertEqual(result["subscriptions"], [])
        self.assertEqual(result["possible_subscriptions"][0]["merchant"], "Card Charge Standing Order")
        self.assertEqual(result["possible_subscriptions"][0]["period"], "monthly")

    def test_dedupes_overlapping_statement_rows(self):
        tx = {
            "bank": "Scotiabank",
            "date": "2026-01-08",
            "description": "POS PURCHASE SPOTIFY AB STOCKHOLM SE",
            "amount": -559.85,
            "balance": None,
            "currency": "JMD",
        }

        self.assertEqual(len(_dedupe_raw_transactions([tx, tx.copy()])), 1)

    def test_three_successive_spotify_charges_become_confirmed(self):
        result = analyze_extracted_subscriptions([
            {
                "bank": "Scotiabank",
                "date": "2026-01-08",
                "description": "POS PURCHASE SPOTIFY AB STOCKHOLM SE",
                "amount": -559.85,
                "balance": None,
                "currency": "JMD",
            },
            {
                "bank": "Scotiabank",
                "date": "2026-02-07",
                "description": "POS PURCHASE SPOTIFY AB STOCKHOLM SE",
                "amount": -559.85,
                "balance": None,
                "currency": "JMD",
            },
            {
                "bank": "Scotiabank",
                "date": "2026-03-09",
                "description": "POS PURCHASE SPOTIFY AB STOCKHOLM SE",
                "amount": -559.85,
                "balance": None,
                "currency": "JMD",
            },
        ])

        self.assertEqual(result["subscriptions"][0]["merchant"], "Spotify")
        self.assertEqual(result["subscriptions"][0]["period"], "monthly")
        self.assertEqual(result["subscriptions"][0]["charge_count"], 3)
        self.assertEqual(result["possible_subscriptions"], [])

    def test_price_change_does_not_block_spotify_subscription(self):
        txns = _classify_transactions([
            _tx("2025-05-30", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -481.80),
            _tx("2025-06-09", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -483.30),
            _tx("2025-07-09", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -483.30),
            _tx("2025-08-18", "POS PURCHASE Spotify P39A3A260C Stockholm SE", -484.65),
            _tx("2025-09-10", "POS PURCHASE Spotify P3A6415FD5 Stockholm SE", -1052.98),
            _tx("2025-10-09", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -567.92),
            _tx("2026-01-08", "POS PURCHASE SPOTIFY AB STOCKHOLM SE", -559.85),
        ])

        subscriptions, _ = _run_subscription_detection(txns)

        self.assertEqual(subscriptions[0]["merchant"], "Spotify")
        self.assertEqual(subscriptions[0]["period"], "monthly")
        self.assertEqual(subscriptions[0]["charge_count"], 7)

    def test_youtube_missing_cycle_still_counts_as_monthly(self):
        txns = _classify_transactions([
            _tx("2025-09-15", "POS PURCHASE Google YouTubePremium Mountain ViewUS", -803.15),
            _tx("2025-10-13", "POS PURCHASE Google YouTubePremium Mountain ViewUS", -804.39),
            _tx("2025-12-29", "POS PURCHASE Google YouTubePremium Mountain ViewUS", -803.20),
            _tx("2026-01-27", "POS PURCHASE Google YouTubePremium Mountain ViewUS", -802.44),
        ])

        subscriptions, _ = _run_subscription_detection(txns)

        self.assertEqual(subscriptions[0]["merchant"], "YouTube")
        self.assertEqual(subscriptions[0]["period"], "monthly")

    def test_unknown_merchant_needs_three_charges_before_review(self):
        txns = _classify_transactions([
            _tx("2026-01-01", "POS PURCHASE SOME DIGITAL SERVICE", -1000.00),
            _tx("2026-02-01", "POS PURCHASE SOME DIGITAL SERVICE", -1000.00),
        ])

        subscriptions, _ = _run_subscription_detection(txns)

        self.assertEqual(subscriptions, [])


if __name__ == "__main__":
    unittest.main()
