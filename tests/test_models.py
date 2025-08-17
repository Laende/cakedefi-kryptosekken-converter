from datetime import datetime
from decimal import Decimal

from src.models import CakeTransaction, KryptosekkenTransaction


class TestCakeTransaction:
    def test_from_csv_row_basic(self, sample_cake_csv_row):
        tx = CakeTransaction.from_csv_row(sample_cake_csv_row)

        assert tx.operation == "Staking reward"
        assert tx.amount == Decimal("0.5197701")
        assert tx.coin_asset == "ETH"
        assert tx.fiat_value == Decimal("1396.0833343587865")
        assert tx.fiat_currency == "USD"
        assert tx.transaction_id == "0x123abc"
        assert tx.reference == "ref123"
        assert tx.withdrawal_address is None
        assert tx.related_reference_id is None

    def test_from_csv_row_with_negative_amount(self, sample_swap_csv_rows):
        # Use the swap fee row from fixture
        swap_fee_row = sample_swap_csv_rows[1]
        tx = CakeTransaction.from_csv_row(swap_fee_row)

        assert tx.operation == "Paid swap fee"
        assert tx.amount == Decimal("-0.00059123685")
        assert tx.fiat_value == Decimal("-1.5908828103729529")
        assert tx.related_reference_id == "dd3b52bc-7eeb-42ef-a194-fad96f751ecd"

    def test_from_csv_row_swap_group(self, sample_swap_csv_rows):
        # Test all three transactions in the swap group
        transactions = [
            CakeTransaction.from_csv_row(row) for row in sample_swap_csv_rows
        ]

        # All should have same related_reference_id and timestamp
        assert len(transactions) == 3
        assert all(
            tx.related_reference_id == "dd3b52bc-7eeb-42ef-a194-fad96f751ecd"
            for tx in transactions
        )

        # Check that they all have the same date (with timezone info)
        expected_date = datetime(2022, 2, 2, 20, 12, 9).replace(
            tzinfo=datetime.fromisoformat("2022-02-02T20:12:09+01:00").tzinfo
        )
        for tx in transactions:
            assert tx.date.replace(microsecond=0) == expected_date.replace(
                microsecond=0
            )

        # Operations should be different
        operations = [tx.operation for tx in transactions]
        assert "Deposit" in operations
        assert "Paid swap fee" in operations
        assert "Withdrew for swap" in operations


class TestKryptosekkenTransaction:
    def test_to_csv_row_income_transaction(self):
        tx = KryptosekkenTransaction(
            tidspunkt=datetime(2022, 2, 2, 19, 36, 32),
            type="Inntekt",
            inn=Decimal("0.5197701"),
            inn_valuta="ETH",
            ut=None,
            ut_valuta=None,
            gebyr=None,
            gebyr_valuta=None,
            marked="CakeDeFi",
            notat="Staking reward",
        )

        row = tx.to_csv_row()

        assert row["Tidspunkt"] == "2022-02-02 19:36:32"
        assert row["Type"] == "Inntekt"
        assert row["Inn"] == "0.5197701"
        assert row["Inn-Valuta"] == "ETH"
        assert row["Ut"] == ""
        assert row["Ut-Valuta"] == ""
        assert row["Gebyr"] == ""
        assert row["Gebyr-Valuta"] == ""
        assert row["Marked"] == "CakeDeFi"
        assert row["Notat"] == "Staking reward"

    def test_to_csv_row_trade_transaction(self):
        tx = KryptosekkenTransaction(
            tidspunkt=datetime(2022, 2, 2, 20, 12, 9),
            type="Handel",
            inn=Decimal("124.82730894"),
            inn_valuta="DFI",
            ut=Decimal("0.11765613315"),
            ut_valuta="ETH",
            gebyr=Decimal("0.00059123685"),
            gebyr_valuta="ETH",
            marked="CakeDeFi",
            notat="Swap ETH to DFI",
        )

        row = tx.to_csv_row()

        assert row["Type"] == "Handel"
        assert row["Inn"] == "124.82730894"
        assert row["Inn-Valuta"] == "DFI"
        assert row["Ut"] == "0.11765613315"
        assert row["Ut-Valuta"] == "ETH"
        assert row["Gebyr"] == "0.00059123685"
        assert row["Gebyr-Valuta"] == "ETH"
