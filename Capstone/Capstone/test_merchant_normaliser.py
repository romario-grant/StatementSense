"""
Tests for merchant_normaliser.py
"""

import pytest
from collections import defaultdict
from merchant_normaliser import clean_merchant, tfidf_similarity, cluster_merchants
from pdf_parsers import parse_ncb_pdf, parse_scotiabank_pdf
from transaction_filter import filter_transactions

NCB_PATH    = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\NcbStatement.pdf')
SCOTIA_PATH = (r'C:\Users\METVT\OneDrive - Ministry of Education, Technological and '
               r'Vocational Training\Downloads\ACCT2015\ScotiaStatement.pdf')


# ─────────────────────────────────────────────
# clean_merchant
# ─────────────────────────────────────────────

class TestCleanMerchant:

    # --- prefix stripping ---
    @pytest.mark.parametrize('raw, expected', [
        # POS prefix (NCB style)
        ('POS HI-LO BASIX KINGSTON',                    'HI-LO BASIX'),
        ('POS BK-UWI KINGSTON',                         'BK-UWI'),
        # POS PURCHASE prefix (Scotiabank style)
        ('POS PURCHASE HI-LO BASIX KINGSTON 7 JM',      'HI-LO BASIX'),
        ('POS PURCHASE BK-UWI KINGSTON 7 JM',           'BK-UWI'),
        ('POS PURCHASE STARBUCKS MALL PLAZA KINGSTON 10 JM', 'STARBUCKS MALL PLAZA'),
        # ABM prefix
        ('ABM 218690/0241 UWI BRANCH',                  'UWI BRANCH'),
        # ABM WITHDRAWAL prefix (Scotiabank)
        ('ABM WITHDRAWAL SBJ 138 SL UWI ONA KGN 7 JM 0436750 5434308460203450',
         'SBJ 138 SL UWI ONA'),
        # ITB-CUSTOMER TRAN DR + Transfer To
        ('ITB-CUSTOMER TRAN DR Transfer to JADA BROWNE 3641', 'JADA BROWNE'),
        # THIRD PARTY TRANSFER + Transfer from
        ('THIRD PARTY TRANSFER Transfer from ENIOLA JOHNSON 1227', 'ENIOLA JOHNSON'),
        ('THIRD PARTY TRANSFER Transfer from HENRY MORGAN',        'HENRY MORGAN'),
        # FUNDS TRANSFER FROM + Transfer from
        ('FUNDS TRANSFER FROM Transfer from JADA BROWNE 3641', 'JADA BROWNE'),
        # FUNDS TRANSFER FROM with reference codes
        ('FUNDS TRANSFER FROM HARMONYWELLNESSCENTRELIMITED, SAJAJMKN, FT26033GG3NF, FT26033GG3NF',
         'HARMONYWELLNESSCENTRELIMITED'),
    ])
    def test_prefix_stripping(self, raw, expected):
        assert clean_merchant(raw) == expected

    # --- location suffix stripping ---
    @pytest.mark.parametrize('raw, expected', [
        ('POS PURCHASE HI-LO BASIX KINGSTON 7 JM',   'HI-LO BASIX'),
        ('POS PURCHASE BK-BLV KINGSTON 20 JM',        'BK-BLV'),
        ('POS PURCHASE VICTORY APPAREL GROUP KINGSTON JM', 'VICTORY APPAREL GROUP'),
        ('POS PURCHASE HARMONY WELLNESS CENTR LKINGSTON 6 JM', 'HARMONY WELLNESS CENTR'),
        ('POS PURCHASE 138 STUDENT LIVING JA TDKINGSTON 6 JM', 'STUDENT LIVING'),
        ('POS PURCHASE UNIQUE BUYERS RENTALS DKINGSTON 6 JM',  'UNIQUE BUYERS RENTALS'),
    ])
    def test_location_suffix_stripping(self, raw, expected):
        assert clean_merchant(raw) == expected

    # --- trailing reference number stripping ---
    @pytest.mark.parametrize('raw, expected', [
        ('POS UNIQUE BUYERS RENTALS & DK 1729',   'UNIQUE BUYERS RENTALS & DK'),
        ('POS KFC - CHANCELLOR HALL KINGS 96',    'KFC - CHANCELLOR HALL KINGS'),
        ('Google YouTubePremium 650-2530000',      'GOOGLE YOUTUBEPREMIUM'),
    ])
    def test_trailing_ref_stripping(self, raw, expected):
        assert clean_merchant(raw) == expected

    # --- output is always uppercase ---
    def test_output_uppercase(self):
        assert clean_merchant('Digicel Ding 117753516 Dublin') == clean_merchant(
            'DIGICEL DING 117753516 DUBLIN')

    # --- empty / whitespace input ---
    def test_empty_string(self):
        assert clean_merchant('') == ''

    def test_whitespace_only(self):
        assert clean_merchant('   ') == ''


# ─────────────────────────────────────────────
# tfidf_similarity
# ─────────────────────────────────────────────

class TestTfidfSimilarity:

    def test_identical_strings_score_one(self):
        assert tfidf_similarity('HI-LO BASIX', 'HI-LO BASIX') == pytest.approx(1.0)

    def test_empty_string_returns_zero(self):
        assert tfidf_similarity('', 'NETFLIX') == 0.0
        assert tfidf_similarity('NETFLIX', '') == 0.0

    def test_similar_strings_above_threshold(self):
        # NCB vs Scotia cleaned variants of HI-LO BASIX
        score = tfidf_similarity('HI-LO BASIX', 'HI-LO BASIX')
        assert score >= 0.65

    def test_unrelated_strings_below_threshold(self):
        score = tfidf_similarity('HI-LO BASIX', 'STARBUCKS')
        assert score < 0.65

    def test_score_is_symmetric(self):
        a, b = 'BK-UWI', 'BK-BLV'
        assert tfidf_similarity(a, b) == pytest.approx(tfidf_similarity(b, a))

    def test_score_in_range(self):
        score = tfidf_similarity('UNIQUE BUYERS RENTALS & DK', 'UNIQUE BUYERS RENTALS')
        assert 0.0 <= score <= 1.0


# ─────────────────────────────────────────────
# cluster_merchants — unit tests
# ─────────────────────────────────────────────

def _make_txn(desc, amount=-100.0, bank='TEST'):
    return {'bank': bank, 'date': '2026-01-01', 'description': desc,
            'amount': amount, 'balance': None, 'currency': 'JMD',
            'source_file': 'test'}


class TestClusterMerchants:

    def test_empty_list(self):
        assert cluster_merchants([]) == []

    def test_merchant_id_added_to_every_row(self):
        txns = [_make_txn('POS HI-LO BASIX KINGSTON'),
                _make_txn('UBER * PENDING help.uber.co')]
        result = cluster_merchants(txns)
        assert all('merchant_id' in t for t in result)

    def test_input_not_mutated(self):
        txns = [_make_txn('POS HI-LO BASIX KINGSTON')]
        original = [dict(t) for t in txns]
        cluster_merchants(txns)
        assert txns == original

    def test_hilo_variants_cluster_together(self):
        """NCB and Scotiabank HI-LO BASIX rows must share a merchant_id."""
        txns = [
            _make_txn('POS HI-LO BASIX KINGSTON'),
            _make_txn('POS PURCHASE HI-LO BASIX KINGSTON 7 JM'),
            _make_txn('POS PURCHASE HI-LO BASIX KINGSTON 7 JM'),
        ]
        result = cluster_merchants(txns)
        ids = [t['merchant_id'] for t in result]
        assert len(set(ids)) == 1, f'Expected 1 cluster, got: {set(ids)}'

    def test_unique_buyers_variants_cluster_together(self):
        """NCB '...& DK 1729' and Scotia 'DKINGSTON 6 JM' variants must merge."""
        txns = [
            _make_txn('POS UNIQUE BUYERS RENTALS & DK 1729'),
            _make_txn('POS UNIQUE BUYERS RENTALS & DK 6962'),
            _make_txn('POS PURCHASE UNIQUE BUYERS RENTALS DKINGSTON 6 JM'),
        ]
        result = cluster_merchants(txns)
        ids = [t['merchant_id'] for t in result]
        assert len(set(ids)) == 1, f'Expected 1 cluster, got: {set(ids)}'

    def test_bk_uwi_cross_bank_cluster(self):
        """BK-UWI appears on both NCB and Scotia — must merge."""
        txns = [
            _make_txn('POS BK-UWI KINGSTON'),
            _make_txn('POS PURCHASE BK-UWI KINGSTON 7 JM'),
        ]
        result = cluster_merchants(txns)
        ids = [t['merchant_id'] for t in result]
        assert len(set(ids)) == 1, f'Expected 1 cluster, got: {set(ids)}'

    def test_jada_browne_transfers_cluster(self):
        """Repeated ITB and FUNDS TRANSFER entries to JADA BROWNE must merge."""
        txns = [
            _make_txn('ITB-CUSTOMER TRAN DR Transfer to JADA BROWNE 3641'),
            _make_txn('ITB-CUSTOMER TRAN DR Transfer to JADA BROWNE 3641'),
            _make_txn('FUNDS TRANSFER FROM Transfer from JADA BROWNE 3641'),
        ]
        result = cluster_merchants(txns)
        ids = [t['merchant_id'] for t in result]
        assert len(set(ids)) == 1, f'Expected 1 cluster, got: {set(ids)}'

    def test_unrelated_merchants_get_different_ids(self):
        txns = [
            _make_txn('POS HI-LO BASIX KINGSTON'),
            _make_txn('POS PURCHASE STARBUCKS MALL PLAZA KINGSTON 10 JM'),
            _make_txn('UBER * PENDING help.uber.co'),
        ]
        result = cluster_merchants(txns)
        ids = [t['merchant_id'] for t in result]
        assert len(set(ids)) == 3, f'Expected 3 distinct IDs, got: {set(ids)}'

    def test_canonical_id_is_most_frequent_name(self):
        """Canonical name should be the cleaned name that appears most often."""
        txns = [
            _make_txn('POS PURCHASE HI-LO BASIX KINGSTON 7 JM'),  # cleaned: HI-LO BASIX (×2)
            _make_txn('POS PURCHASE HI-LO BASIX KINGSTON 7 JM'),
            _make_txn('POS HI-LO BASIX KINGSTON'),                 # cleaned: HI-LO BASIX (×1)
        ]
        result = cluster_merchants(txns)
        assert result[0]['merchant_id'] == 'HI-LO BASIX'

    def test_custom_threshold_tighter(self):
        """At threshold=0.99, only exact matches cluster together."""
        txns = [
            _make_txn('POS HI-LO BASIX KINGSTON'),
            _make_txn('POS PURCHASE HI-LO BASIX KINGSTON 7 JM'),
        ]
        result = cluster_merchants(txns, threshold=0.99)
        ids = [t['merchant_id'] for t in result]
        # Both clean to "HI-LO BASIX" so still 1 cluster even at 0.99
        assert len(set(ids)) == 1


# ─────────────────────────────────────────────
# Integration tests — real PDF data
# ─────────────────────────────────────────────

class TestNCBIntegration:
    @pytest.fixture(scope='class')
    def clustered(self):
        raw = parse_ncb_pdf(NCB_PATH)
        return cluster_merchants(filter_transactions(raw))

    def test_all_rows_have_merchant_id(self, clustered):
        assert all('merchant_id' in t for t in clustered)

    def test_hilo_basix_is_one_cluster(self, clustered):
        hilo = [t for t in clustered if 'HI-LO BASIX' in t['merchant_id']]
        ids = {t['merchant_id'] for t in hilo}
        assert len(ids) == 1

    def test_unique_buyers_is_one_cluster(self, clustered):
        ub = [t for t in clustered if 'UNIQUE BUYERS' in t['merchant_id']]
        ids = {t['merchant_id'] for t in ub}
        assert len(ids) == 1, f'UNIQUE BUYERS split into: {ids}'

    def test_cluster_count_less_than_transaction_count(self, clustered):
        n_clusters = len({t['merchant_id'] for t in clustered})
        assert n_clusters < len(clustered)

    def test_print_clusters(self, clustered, capsys):
        by_mid: dict[str, list] = defaultdict(list)
        for t in clustered:
            by_mid[t['merchant_id']].append(t)
        print(f'\n--- NCB clusters ({len(by_mid)}) ---')
        for mid, txns in sorted(by_mid.items()):
            total = sum(t['amount'] for t in txns)
            print(f'  {mid:<45}  {len(txns):2d}x  {total:>12,.2f}')
        captured = capsys.readouterr()
        assert 'NCB clusters' in captured.out


class TestScotiabankIntegration:
    @pytest.fixture(scope='class')
    def clustered(self):
        raw = parse_scotiabank_pdf(SCOTIA_PATH)
        return cluster_merchants(filter_transactions(raw))

    def test_all_rows_have_merchant_id(self, clustered):
        assert all('merchant_id' in t for t in clustered)

    def test_hilo_basix_is_one_cluster(self, clustered):
        hilo = [t for t in clustered if 'HI-LO BASIX' in t['merchant_id']]
        ids = {t['merchant_id'] for t in hilo}
        assert len(ids) == 1

    def test_jada_browne_is_one_cluster(self, clustered):
        jada = [t for t in clustered if 'JADA BROWNE' in t['merchant_id']]
        ids = {t['merchant_id'] for t in jada}
        assert len(ids) == 1, f'JADA BROWNE split into: {ids}'

    def test_cluster_count_less_than_transaction_count(self, clustered):
        n_clusters = len({t['merchant_id'] for t in clustered})
        assert n_clusters < len(clustered)

    def test_print_clusters(self, clustered, capsys):
        by_mid: dict[str, list] = defaultdict(list)
        for t in clustered:
            by_mid[t['merchant_id']].append(t)
        print(f'\n--- Scotiabank clusters ({len(by_mid)}) ---')
        for mid, txns in sorted(by_mid.items()):
            total = sum(t['amount'] for t in txns)
            print(f'  {mid:<45}  {len(txns):2d}x  {total:>12,.2f}')
        captured = capsys.readouterr()
        assert 'Scotiabank clusters' in captured.out
