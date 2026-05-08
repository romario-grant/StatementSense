"""
Tests for transaction_filter.py
"""

import pytest
from transaction_filter import filter_transactions, is_noise_row
from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf

NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')


# ─────────────────────────────────────────────
# is_noise_row — unit tests
# ─────────────────────────────────────────────

class TestIsNoiseRow:
    # --- rows that MUST be filtered ---
    @pytest.mark.parametrize('desc', [
        'SERVICE CHARGE BK-UWI KINGSTON 7 JM For 03FEB',
        'service charge monthly',
        'GCT/GOVT TAX ON SERVICE CHARGE OF 27.65',
        'GCT on POS Tx Fee',
        'GCT on Decline Tx Fee:05-01-2026',
        'POS Tx Fee',
        'Decline Trxn Fee Google YouTubePremi',
        'Decline Tx Fee Reference 123',
        'STAMP DUTY',
        'Withholding Tax on Interest',
        'Record Keeping Fee',
        'ABM Fee',
    ])
    def test_noise_rows_are_detected(self, desc):
        assert is_noise_row(desc) is True

    # --- merchant rows that MUST pass through ---
    @pytest.mark.parametrize('desc', [
        'NETFLIX.COM',
        'UBER * PENDING help.uber.co',
        'POS HI-LO BASIX KINGSTON',
        'POS PURCHASE BK-UWI KINGSTON 7 JM',
        'FUNDS TRANSFER FROM HARMONYWELLNESSCENTRELIMI',
        'Google YouTubePremium 650-2530000',
        'ELink TRF-TO DC BLOSSOMS JA',
        'ABM 218690/0241 UWI BRANCH',
        'ITB-CUSTOMER TRAN DR Transfer to JADA BROWNE',
        'THIRD PARTY TRANSFER Transfer from HENRY MORG',
        'STARBUCKS MALL PLAZA KINGSTON',
        'Digicel Ding 117753516 Dublin',
    ])
    def test_merchant_rows_pass_through(self, desc):
        assert is_noise_row(desc) is False


# ─────────────────────────────────────────────
# filter_transactions — unit tests
# ─────────────────────────────────────────────

class TestFilterTransactions:
    def _make_txn(self, desc, amount=-100.0):
        return {'bank': 'TEST', 'date': '2026-01-01',
                'description': desc, 'amount': amount,
                'balance': None, 'currency': 'JMD', 'source_file': 'test'}

    def test_noise_rows_removed(self):
        txns = [
            self._make_txn('SERVICE CHARGE HI-LO'),
            self._make_txn('GCT/GOVT TAX ON SERVICE CHARGE OF 27.65'),
            self._make_txn('POS Tx Fee'),
        ]
        assert filter_transactions(txns) == []

    def test_merchant_rows_kept(self):
        txns = [
            self._make_txn('NETFLIX.COM', -1500.0),
            self._make_txn('POS HI-LO BASIX KINGSTON', -3491.81),
            self._make_txn('UBER * PENDING help.uber.co', -1086.96),
        ]
        result = filter_transactions(txns)
        assert len(result) == 3

    def test_mixed_list_filtered_correctly(self):
        txns = [
            self._make_txn('NETFLIX.COM', -1500.0),           # keep
            self._make_txn('SERVICE CHARGE NETFLIX'),          # remove
            self._make_txn('GCT on POS Tx Fee', -2.70),       # remove
            self._make_txn('UBER * PENDING help.uber.co'),     # keep
            self._make_txn('Decline Trxn Fee Google'),         # remove
        ]
        result = filter_transactions(txns)
        assert len(result) == 2
        assert result[0]['description'] == 'NETFLIX.COM'
        assert result[1]['description'] == 'UBER * PENDING help.uber.co'

    def test_input_not_mutated(self):
        txns = [self._make_txn('SERVICE CHARGE X')]
        original_len = len(txns)
        filter_transactions(txns)
        assert len(txns) == original_len

    def test_empty_list(self):
        assert filter_transactions([]) == []


# ─────────────────────────────────────────────
# Integration tests — real PDF data
# ─────────────────────────────────────────────

class TestNCBIntegration:
    @pytest.fixture(scope='class')
    def ncb_txns(self):
        return parse_ncb_pdf(NCB_PATH)

    @pytest.fixture(scope='class')
    def filtered(self, ncb_txns):
        return filter_transactions(ncb_txns)

    def test_filter_reduces_count(self, ncb_txns, filtered):
        assert len(filtered) < len(ncb_txns)

    def test_no_noise_in_output(self, filtered):
        noise = [t for t in filtered if is_noise_row(t['description'])]
        assert noise == [], f"Noise rows leaked through: {[n['description'] for n in noise]}"

    def test_known_merchants_present(self, filtered):
        descs = [t['description'] for t in filtered]
        assert any('HI-LO' in d for d in descs)
        assert any('UBER' in d for d in descs)
        assert any('YouTubePremium' in d or 'YouTube' in d for d in descs)

    def test_abm_withdrawal_kept(self, filtered):
        assert any('ABM' in t['description'] for t in filtered)


class TestScotiabankIntegration:
    @pytest.fixture(scope='class')
    def sc_txns(self):
        return parse_scotiabank_pdf(SCOTIA_PATH)

    @pytest.fixture(scope='class')
    def filtered(self, sc_txns):
        return filter_transactions(sc_txns)

    def test_filter_reduces_count(self, sc_txns, filtered):
        assert len(filtered) < len(sc_txns)

    def test_no_noise_in_output(self, filtered):
        noise = [t for t in filtered if is_noise_row(t['description'])]
        assert noise == [], f"Noise rows leaked through: {[n['description'] for n in noise]}"

    def test_known_merchants_present(self, filtered):
        descs = [t['description'] for t in filtered]
        assert any('HI-LO' in d for d in descs)
        assert any('BK-UWI' in d for d in descs)

    def test_transfers_kept(self, filtered):
        assert any('TRANSFER' in t['description'].upper() for t in filtered)
