from datetime import datetime
from decimal import Decimal
import io
from pathlib import Path
import sys
from typing import Any

import pytest

from src.currency_converter import CurrencyConverter
from src.models import CakeTransaction
from src.transaction_grouper import TransactionGroup, TransactionGrouper


class TestTransactionGrouper:
    @pytest.fixture
    def currency_converter(self):
        """Create currency converter for testing"""
        exr_file = Path(__file__).parent.parent / "src" / "data" / "EXR.csv"
        return CurrencyConverter(exr_file)

    @pytest.fixture
    def grouper(self, currency_converter: CurrencyConverter):
        """Create transaction grouper"""
        return TransactionGrouper(currency_converter)

    @pytest.fixture
    def sample_staking_rewards(self):
        """Sample staking reward transactions for same day"""
        return [
            CakeTransaction(
                date=datetime(2022, 2, 3, 2, 34, 42),
                operation="Staking reward",
                amount=Decimal("0.00917367"),
                coin_asset="DFI",
                fiat_value=Decimal("0.0230499643513991"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="cff07793-3a55-45f1-9fcc-0664b59bf75f",
                related_reference_id=None,
            ),
            CakeTransaction(
                date=datetime(2022, 2, 3, 14, 35, 24),
                operation="Staking reward",
                amount=Decimal("0.0091062"),
                coin_asset="DFI",
                fiat_value=Decimal("0.0225381978273431"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="c7888e02-7005-4234-be3c-ec0b191f76e6",
                related_reference_id=None,
            ),
        ]

    def test_group_single_transaction(
        self, grouper: TransactionGrouper, sample_cake_csv_row: dict[str, Any]
    ):
        """Test grouping single transaction"""
        tx = CakeTransaction.from_csv_row(sample_cake_csv_row)
        groups = grouper.group_transactions([tx])

        assert len(groups) == 1
        assert groups[0].group_type == "single"
        assert groups[0].total_participants == 1
        assert groups[0].transactions[0] == tx

    def test_group_daily_rewards(
        self, grouper: TransactionGrouper, sample_staking_rewards: list[CakeTransaction]
    ):
        """Test grouping daily staking rewards"""
        groups = grouper.group_transactions(sample_staking_rewards)

        # Should create one group for the two staking rewards
        assert len(groups) == 1
        assert groups[0].group_type == "daily_rewards"
        assert groups[0].total_participants == 2

        # Check transactions are sorted by timestamp
        timestamps = [tx.date for tx in groups[0].transactions]
        assert timestamps == sorted(timestamps)

    def test_group_swap_transactions(
        self, grouper: TransactionGrouper, sample_swap_csv_rows
    ):
        """Test grouping swap transactions by related_reference_id"""
        transactions = [
            CakeTransaction.from_csv_row(row) for row in sample_swap_csv_rows
        ]
        groups = grouper.group_transactions(transactions)

        # Should create one swap group
        assert len(groups) == 1
        assert groups[0].group_type == "swap"
        assert groups[0].total_participants == 3
        assert groups[0].reference_id == "dd3b52bc-7eeb-42ef-a194-fad96f751ecd"

    def test_mixed_transaction_grouping(
        self,
        grouper: TransactionGrouper,
        sample_staking_rewards: list[CakeTransaction],
        sample_swap_csv_rows,
    ):
        """Test grouping mix of transaction types"""
        # Combine different transaction types
        swap_transactions = [
            CakeTransaction.from_csv_row(row) for row in sample_swap_csv_rows
        ]
        all_transactions = sample_staking_rewards + swap_transactions

        groups = grouper.group_transactions(all_transactions)

        # Should have one swap group and one daily rewards group
        assert len(groups) == 2

        group_types = [g.group_type for g in groups]
        assert "swap" in group_types
        assert "daily_rewards" in group_types

    def test_convert_single_income_transaction(
        self, grouper: TransactionGrouper, sample_cake_csv_row
    ):
        """Test converting single income transaction"""
        tx = CakeTransaction.from_csv_row(sample_cake_csv_row)
        group = TransactionGroup([tx], "single")

        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        assert ks_tx.type == "Inntekt"
        assert ks_tx.inn == Decimal("0.5197701")
        assert ks_tx.inn_valuta == "ETH"
        assert ks_tx.ut is None  # Fixed: Income doesn't create outflow
        assert ks_tx.ut_valuta is None  # Fixed: No currency spent for income
        assert ks_tx.marked == "CakeDeFi"
        assert "Staking reward" in ks_tx.notat  # Note contains operation and NOK value
        assert "NOK value:" in ks_tx.notat  # NOK valuation is in note for tax reference

    def test_convert_daily_rewards_group(
        self, grouper: TransactionGrouper, sample_staking_rewards: list[CakeTransaction]
    ):
        """Test converting aggregated daily rewards"""
        group = TransactionGroup(sample_staking_rewards, "daily_rewards")

        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        assert ks_tx.type == "Inntekt"
        # Should sum up the amounts
        expected_total = sum(tx.amount for tx in sample_staking_rewards)
        assert ks_tx.inn == expected_total
        assert ks_tx.inn_valuta == "DFI"
        assert ks_tx.ut is None  # Fixed: Income doesn't create outflow
        assert ks_tx.ut_valuta is None  # Fixed: No currency spent for grouped income
        assert "Daily DFI rewards" in ks_tx.notat
        assert "2 txs" in ks_tx.notat
        assert "NOK value:" in ks_tx.notat  # NOK valuation is in note for tax reference

    def test_income_transaction_no_phantom_nok_outflow(
        self, grouper: TransactionGrouper
    ):
        """Test that income transactions don't create phantom NOK outflows"""

        # Create income transaction
        income_tx = CakeTransaction(
            date=datetime(2022, 2, 2, 19, 36, 32),
            operation="Staking reward",
            amount=Decimal("0.5197701"),  # Positive = receiving crypto
            coin_asset="ETH",
            fiat_value=Decimal("1396.08"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="ref123",
            related_reference_id=None,
        )

        group = TransactionGroup([income_tx], "single")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Verify no phantom NOK outflow
        assert ks_tx.type == "Inntekt"
        assert ks_tx.inn == Decimal("0.5197701")
        assert ks_tx.inn_valuta == "ETH"
        assert ks_tx.ut is None, "Income should not have Ut (no outflow)"
        assert ks_tx.ut_valuta is None, "Income should not have Ut-Valuta"

        # Verify NOK valuation is in note for tax purposes
        assert "NOK value:" in ks_tx.notat
        assert "Staking reward" in ks_tx.notat

    def test_grouped_income_no_phantom_nok_outflow(self, grouper: TransactionGrouper):
        """Test that grouped income transactions don't create phantom NOK outflows"""

        # Create multiple income transactions from same day (will be grouped)
        reward1 = CakeTransaction(
            date=datetime(2022, 2, 3, 2, 34, 42),
            operation="Staking reward",
            amount=Decimal("0.18761683"),
            coin_asset="DFI",
            fiat_value=Decimal("4.05"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="ref456",
            related_reference_id=None,
        )

        reward2 = CakeTransaction(
            date=datetime(2022, 2, 3, 2, 35, 15),
            operation="Liquidity mining reward ETH-DFI",
            amount=Decimal("0.0000010151691372"),
            coin_asset="DFI",
            fiat_value=Decimal("0.02"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="ref789",
            related_reference_id=None,
        )

        # Create daily rewards group
        group = TransactionGroup([reward1, reward2], "daily_rewards")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Verify no phantom NOK outflow for grouped income
        assert ks_tx.type == "Inntekt"
        expected_total = reward1.amount + reward2.amount
        assert ks_tx.inn == expected_total
        assert ks_tx.inn_valuta == "DFI"
        assert ks_tx.ut is None, "Grouped income should not have Ut (no outflow)"
        assert ks_tx.ut_valuta is None, "Grouped income should not have Ut-Valuta"

        # Verify NOK valuation is in note
        assert "NOK value:" in ks_tx.notat
        assert "Daily DFI rewards" in ks_tx.notat

    def test_liquidity_grouping_with_result_transaction(
        self, grouper: TransactionGrouper
    ):
        """Test that liquidity operations are properly grouped including result transactions"""

        # Create a complete liquidity operation set based on real patterns
        group_id = "test-liquidity-group-123"

        # Input transactions (related_reference_id = group_id)
        add_liquidity_dfi = CakeTransaction(
            date=datetime(2022, 2, 2, 20, 12, 9),
            operation="Add liquidity ETH-DFI",
            amount=Decimal("-124.82730879"),  # Negative = spending
            coin_asset="DFI",
            fiat_value=Decimal("314.84"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="input-ref-1",
            related_reference_id=group_id,  # Links to group
        )

        add_liquidity_eth = CakeTransaction(
            date=datetime(2022, 2, 2, 20, 12, 9),
            operation="Add liquidity ETH-DFI",
            amount=Decimal("-0.1174197278085303"),  # Negative = spending
            coin_asset="ETH",
            fiat_value=Decimal("315.83"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="input-ref-2",
            related_reference_id=group_id,  # Links to group
        )

        # Result transaction (reference = group_id) - use closer timestamp to avoid time-based splitting
        added_liquidity_result = CakeTransaction(
            date=datetime(
                2022, 2, 2, 20, 15, 0
            ),  # Within 5 minutes of input transactions
            operation="Added liquidity",
            amount=Decimal("3.82564708"),  # Positive = receiving LP tokens
            coin_asset="ETH-DFI",
            fiat_value=Decimal("630.67"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference=group_id,  # Links back to group
            related_reference_id=None,
        )

        transactions = [add_liquidity_dfi, add_liquidity_eth, added_liquidity_result]

        # Group the transactions
        groups = grouper.group_transactions(transactions)

        # Should create one add_liquidity group with all 3 transactions
        liquidity_groups = [g for g in groups if g.group_type == "add_liquidity"]
        assert len(liquidity_groups) == 1, (
            f"Expected 1 add_liquidity group, got {len(liquidity_groups)}"
        )

        liquidity_group = liquidity_groups[0]
        assert len(liquidity_group.transactions) == 3, (
            f"Expected 3 transactions in group, got {len(liquidity_group.transactions)}"
        )

        # Verify all transactions are included
        operations = [tx.operation for tx in liquidity_group.transactions]
        assert "Add liquidity ETH-DFI" in operations
        assert "Added liquidity" in operations
        assert operations.count("Add liquidity ETH-DFI") == 2  # Two input transactions

        # Convert to kryptosekken format
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(liquidity_group)

        # Should create one complete trade transaction
        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Verify the trade is complete (has both Inn and Ut)
        assert ks_tx.type == "Handel"
        assert ks_tx.inn is not None, (
            "Liquidity trade should have Inn (LP tokens received)"
        )
        assert ks_tx.inn_valuta == "ETH-DFI", (
            f"Expected ETH-DFI LP tokens, got {ks_tx.inn_valuta}"
        )
        assert ks_tx.ut is not None, "Liquidity trade should have Ut (assets spent)"
        assert ks_tx.ut_valuta is not None, "Liquidity trade should have Ut currency"

    def test_liquidity_grouping_without_result_transaction(
        self, grouper: TransactionGrouper
    ):
        """Test that incomplete liquidity operations are handled gracefully"""

        # Create incomplete liquidity operation (missing "Added liquidity" result)
        group_id = "incomplete-liquidity-group-456"

        add_liquidity_dfi = CakeTransaction(
            date=datetime(2022, 2, 2, 20, 12, 9),
            operation="Add liquidity ETH-DFI",
            amount=Decimal("-124.82730879"),
            coin_asset="DFI",
            fiat_value=Decimal("314.84"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="input-ref-1",
            related_reference_id=group_id,
        )

        transactions = [add_liquidity_dfi]

        # Group the transactions
        groups = grouper.group_transactions(transactions)

        # Should create one group, but it will be incomplete
        liquidity_groups = [g for g in groups if g.group_type == "add_liquidity"]
        assert len(liquidity_groups) == 1, (
            f"Expected 1 add_liquidity group, got {len(liquidity_groups)}"
        )

        # The group should handle incomplete liquidity operations gracefully
        liquidity_group = liquidity_groups[0]
        assert len(liquidity_group.transactions) == 1

        # With our fix, incomplete asset contributions are skipped to prevent double-spending
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(liquidity_group)
        assert len(kryptosekken_txs) == 0, (
            "Incomplete asset contributions should be skipped to prevent double-spending"
        )

    def test_entered_earn_operation_as_transfer(self, grouper: TransactionGrouper):
        """Test that 'Entered Earn' operations are converted to transfers, not incomplete trades"""

        # Create "Entered Earn" transaction (negative amount = spending crypto)
        entered_earn_tx = CakeTransaction(
            date=datetime(2022, 9, 24, 2, 4, 10),
            operation="Entered Earn",
            amount=Decimal("-0.00616777"),  # Negative = spending crypto
            coin_asset="BTC",
            fiat_value=Decimal("120.50"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="earn-ref-1",
            related_reference_id=None,
        )

        group = TransactionGroup([entered_earn_tx], "single")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Should be converted to transfer out (not incomplete trade)
        assert ks_tx.type == "Overføring-Ut", (
            f"Expected Overføring-Ut, got {ks_tx.type}"
        )
        assert ks_tx.inn is None, "Transfer out should not have Inn"
        assert ks_tx.inn_valuta is None, "Transfer out should not have Inn-Valuta"
        assert ks_tx.ut == Decimal("0.00616777"), (
            f"Expected positive Ut amount, got {ks_tx.ut}"
        )
        assert ks_tx.ut_valuta == "BTC", f"Expected BTC, got {ks_tx.ut_valuta}"
        assert "Entered Earn" in ks_tx.notat
        assert "incomplete DeFi op" in ks_tx.notat

    def test_liquidity_removal_grouping_and_conversion(
        self, grouper: TransactionGrouper
    ):
        """Test that liquidity removal operations are properly grouped and converted"""

        # Create a complete liquidity removal operation set based on real 2023 patterns
        group_id = "test-removal-group-789"

        # Input transactions: Remove liquidity (positive amounts = receiving crypto)
        remove_btc = CakeTransaction(
            date=datetime(2023, 10, 5, 12, 29, 11),
            operation="Remove liquidity BTC-DFI",
            amount=Decimal("0.00417787"),  # Positive = receiving BTC
            coin_asset="BTC",
            fiat_value=Decimal("115.62"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="input-ref-1",
            related_reference_id=group_id,
        )

        remove_dfi = CakeTransaction(
            date=datetime(2023, 10, 5, 12, 29, 11),
            operation="Remove liquidity BTC-DFI",
            amount=Decimal("403.44711865"),  # Positive = receiving DFI
            coin_asset="DFI",
            fiat_value=Decimal("115.62"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="input-ref-2",
            related_reference_id=group_id,
        )

        # Result transaction: Removed liquidity (negative amount = spending LP tokens)
        removed_liquidity_result = CakeTransaction(
            date=datetime(2023, 10, 5, 12, 29, 11),
            operation="Removed liquidity",
            amount=Decimal("-1.30755234"),  # Negative = spending LP tokens
            coin_asset="BTC-DFI",
            fiat_value=Decimal("-231.24"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference=group_id,  # Links back to group
            related_reference_id=None,
        )

        transactions = [remove_btc, remove_dfi, removed_liquidity_result]

        # Group the transactions
        groups = grouper.group_transactions(transactions)

        # Debug: Print all groups created
        print(f"\nDEBUG: Total groups created: {len(groups)}")
        for i, group in enumerate(groups):
            print(
                f"  Group {i}: type={group.group_type}, ref_id={group.reference_id}, transactions={len(group.transactions)}"
            )
            for tx in group.transactions:
                print(
                    f"    - {tx.operation} ({tx.coin_asset}) ref={tx.reference} related_ref={tx.related_reference_id}"
                )

        # Should create one remove_liquidity group with all 3 transactions
        liquidity_groups = [g for g in groups if g.group_type == "remove_liquidity"]
        assert len(liquidity_groups) == 1, (
            f"Expected 1 remove_liquidity group, got {len(liquidity_groups)}. All groups: {[(g.group_type, len(g.transactions)) for g in groups]}"
        )

        liquidity_group = liquidity_groups[0]
        assert len(liquidity_group.transactions) == 3, (
            f"Expected 3 transactions in group, got {len(liquidity_group.transactions)}"
        )

        # Convert to kryptosekken format
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(liquidity_group)

        # Should create one complete trade transaction
        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Verify the removal trade is complete
        assert ks_tx.type == "Handel"

        # Should receive crypto assets (Inn)
        assert ks_tx.inn is not None, (
            "Liquidity removal should have Inn (crypto received)"
        )
        assert ks_tx.inn_valuta in ["BTC", "DFI"], (
            f"Expected BTC or DFI, got {ks_tx.inn_valuta}"
        )

        # Should spend LP tokens (Ut)
        assert ks_tx.ut == Decimal("1.30755234"), (
            f"Expected LP token amount spent, got {ks_tx.ut}"
        )
        assert ks_tx.ut_valuta == "BTC-DFI", (
            f"Expected BTC-DFI LP tokens, got {ks_tx.ut_valuta}"
        )

        # Should have second asset as gebyr (fee field used for second asset)
        assert ks_tx.gebyr is not None, "Should have second asset in gebyr field"
        assert ks_tx.gebyr_valuta in ["BTC", "DFI"], (
            f"Expected BTC or DFI in gebyr, got {ks_tx.gebyr_valuta}"
        )

        # Verify note
        assert "Remove liquidity" in ks_tx.notat

    def test_convert_swap_group(
        self, grouper: TransactionGrouper, sample_swap_csv_rows
    ):
        """Test converting swap transaction group"""
        transactions = [
            CakeTransaction.from_csv_row(row) for row in sample_swap_csv_rows
        ]
        group = TransactionGroup(
            transactions, "swap", "dd3b52bc-7eeb-42ef-a194-fad96f751ecd"
        )

        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        assert ks_tx.type == "Handel"
        assert ks_tx.inn is not None  # Should have incoming asset (DFI)
        assert ks_tx.ut is not None  # Should have outgoing asset (ETH)
        assert ks_tx.gebyr is not None  # Should have fee
        assert ks_tx.marked == "CakeDeFi"
        assert "Swap from" in ks_tx.notat and "txs" in ks_tx.notat

    def test_groups_are_sorted_by_timestamp(self, grouper: TransactionGrouper):
        """Test that groups are returned sorted by timestamp"""
        # Create transactions with different dates
        early_tx = CakeTransaction(
            date=datetime(2022, 1, 1, 12, 0, 0),
            operation="Staking reward",
            amount=Decimal("1.0"),
            coin_asset="DFI",
            fiat_value=Decimal("2.5"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="early",
            related_reference_id=None,
        )

        late_tx = CakeTransaction(
            date=datetime(2022, 2, 1, 12, 0, 0),
            operation="Staking reward",
            amount=Decimal("1.0"),
            coin_asset="DFI",
            fiat_value=Decimal("2.5"),
            fiat_currency="USD",
            transaction_id=None,
            withdrawal_address=None,
            reference="late",
            related_reference_id=None,
        )

        # Pass in wrong order
        groups = grouper.group_transactions([late_tx, early_tx])

        # Should be sorted by timestamp
        assert len(groups) == 2
        assert groups[0].timestamp < groups[1].timestamp

    def test_convert_complete_swap_group(self, grouper: TransactionGrouper):
        """Test converting a complete swap group with deposit, withdrawal, and fee"""

        # Create a complete swap: withdraw ETH, pay fee, deposit DFI
        transactions = [
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Withdrew for swap",
                amount=Decimal("-0.1912517957"),
                coin_asset="ETH",
                fiat_value=Decimal("500.0"),
                fiat_currency="USD",
                transaction_id="swap1",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref123",
            ),
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Paid swap fee",
                amount=Decimal("-0.0009610643"),
                coin_asset="ETH",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id="swap2",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref123",
            ),
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 32),
                operation="Deposit",
                amount=Decimal("32.79387452"),
                coin_asset="DFI",
                fiat_value=Decimal("502.5"),
                fiat_currency="USD",
                transaction_id="swap3",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref123",
            ),
        ]

        group = TransactionGroup(transactions, "swap", "ref123")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Should be a complete trade
        assert ks_tx.type == "Handel"
        assert ks_tx.inn == Decimal("32.79387452")  # DFI received
        assert ks_tx.inn_valuta == "DFI"
        assert ks_tx.ut == Decimal("0.1912517957")  # ETH withdrawn
        assert ks_tx.ut_valuta == "ETH"
        assert ks_tx.gebyr == Decimal("0.0009610643")  # ETH fee
        assert ks_tx.gebyr_valuta == "ETH"
        assert "Swap from 3 txs" in ks_tx.notat

    def test_convert_incomplete_swap_group_fallback(self, grouper: TransactionGrouper):
        """Test that incomplete swap groups fall back to individual safe transactions"""

        # Create incomplete swap: only withdrawal and fee, no deposit
        transactions = [
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Withdrew for swap",
                amount=Decimal("-0.1912517957"),
                coin_asset="ETH",
                fiat_value=Decimal("500.0"),
                fiat_currency="USD",
                transaction_id="swap1",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref123",
            ),
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Paid swap fee",
                amount=Decimal("-0.0009610643"),
                coin_asset="ETH",
                fiat_value=Decimal("2.5"),
                fiat_currency="USD",
                transaction_id="swap2",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref123",
            ),
        ]

        # Capture warning output
        captured_output = io.StringIO()
        sys.stdout = captured_output

        group = TransactionGroup(transactions, "swap", "ref123")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        # Restore stdout
        sys.stdout = sys.__stdout__

        # Should fall back to individual transactions
        assert len(kryptosekken_txs) == 2

        # First should be transfer out (withdrew for swap)
        tx1 = kryptosekken_txs[0]
        assert tx1.type == "Overføring-Ut"
        assert tx1.ut == Decimal("0.1912517957")
        assert tx1.ut_valuta == "ETH"
        assert tx1.inn is None
        assert tx1.inn_valuta is None

        # Second should be management cost (paid swap fee)
        tx2 = kryptosekken_txs[1]
        assert tx2.type == "Forvaltningskostnad"
        assert tx2.ut == Decimal("0.0009610643")
        assert tx2.ut_valuta == "ETH"
        assert tx2.inn is None
        assert tx2.inn_valuta is None

        # Should have printed warning
        assert "WARNING: Complex/unresolvable group" in captured_output.getvalue()

    def test_convert_swap_group_multiple_currencies(self, grouper: TransactionGrouper):
        """Test swap group with multiple currencies (complex swap)"""

        transactions = [
            # Withdraw multiple assets
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Withdrew for swap",
                amount=Decimal("-0.1"),
                coin_asset="ETH",
                fiat_value=Decimal("300.0"),
                fiat_currency="USD",
                transaction_id="swap1",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref456",
            ),
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Withdrew for swap",
                amount=Decimal("-0.05"),
                coin_asset="ETH",
                fiat_value=Decimal("150.0"),
                fiat_currency="USD",
                transaction_id="swap2",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref456",
            ),
            # Multiple fees in different currencies
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Paid swap fee",
                amount=Decimal("-0.001"),
                coin_asset="ETH",
                fiat_value=Decimal("3.0"),
                fiat_currency="USD",
                transaction_id="swap3",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref456",
            ),
            # Deposit
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 32),
                operation="Deposit",
                amount=Decimal("100.0"),
                coin_asset="DFI",
                fiat_value=Decimal("453.0"),
                fiat_currency="USD",
                transaction_id="swap4",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref456",
            ),
        ]

        group = TransactionGroup(transactions, "swap", "ref456")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Should aggregate properly
        assert ks_tx.type == "Handel"
        assert ks_tx.inn == Decimal("100.0")  # DFI deposit
        assert ks_tx.inn_valuta == "DFI"
        assert ks_tx.ut == Decimal("0.15")  # Sum of ETH withdrawals (0.1 + 0.05)
        assert ks_tx.ut_valuta == "ETH"
        assert ks_tx.gebyr == Decimal("0.001")  # ETH fee
        assert ks_tx.gebyr_valuta == "ETH"

    def test_convert_swap_group_fee_only_becomes_ut(self, grouper: TransactionGrouper):
        """Test swap group where fee becomes the main Ut when no withdrawal exists"""

        transactions = [
            # Only fee, no separate withdrawal
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Paid swap fee",
                amount=Decimal("-0.001"),
                coin_asset="ETH",
                fiat_value=Decimal("3.0"),
                fiat_currency="USD",
                transaction_id="swap1",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref789",
            ),
            # Deposit
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 32),
                operation="Deposit",
                amount=Decimal("10.0"),
                coin_asset="DFI",
                fiat_value=Decimal("3.0"),
                fiat_currency="USD",
                transaction_id="swap2",
                withdrawal_address=None,
                reference=None,
                related_reference_id="ref789",
            ),
        ]

        group = TransactionGroup(transactions, "swap", "ref789")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        # Incomplete swap groups fall back to individual transactions for safety
        assert len(kryptosekken_txs) == 2

        # First should be the fee (management cost)
        fee_tx = kryptosekken_txs[0]
        assert fee_tx.type == "Forvaltningskostnad"
        assert fee_tx.ut == Decimal("0.001")
        assert fee_tx.ut_valuta == "ETH"
        assert fee_tx.inn is None
        assert fee_tx.inn_valuta is None

        # Second should be the deposit (acquisition - affects balance)
        deposit_tx = kryptosekken_txs[1]
        assert deposit_tx.type == "Erverv"  # Deposit is now acquisition
        assert deposit_tx.inn == Decimal("10.0")
        assert deposit_tx.inn_valuta == "DFI"
        assert deposit_tx.ut is None
        assert deposit_tx.ut_valuta is None

    def test_convert_buy_token_group(self, grouper: TransactionGrouper):
        """Test converting Buy token trade group (positive and negative sides)"""

        # Typical Buy token scenario: negative BTC out, positive DFI in
        transactions = [
            CakeTransaction(
                date=datetime(2024, 10, 25, 4, 48, 49),
                operation="Buy token",
                amount=Decimal("-0.00001"),  # Negative = outgoing BTC
                coin_asset="BTC",
                fiat_value=Decimal("0.50"),
                fiat_currency="USD",
                transaction_id="buy1",
                withdrawal_address=None,
                reference="ref1",
                related_reference_id="buy-group-123",
            ),
            CakeTransaction(
                date=datetime(2024, 10, 25, 4, 48, 49),
                operation="Buy token",
                amount=Decimal("0.00000577"),  # Positive = incoming DFI
                coin_asset="DFI",
                fiat_value=Decimal("9.56914254E-8"),
                fiat_currency="USD",
                transaction_id="buy2",
                withdrawal_address=None,
                reference="ref2",
                related_reference_id="buy-group-123",
            ),
        ]

        group = TransactionGroup(transactions, "swap", "buy-group-123")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Should be a complete trade
        assert ks_tx.type == "Handel"
        assert ks_tx.inn == Decimal("0.00000577")  # DFI received (positive amount)
        assert ks_tx.inn_valuta == "DFI"
        assert ks_tx.ut == Decimal(
            "0.00001"
        )  # BTC paid (negative amount, now positive)
        assert ks_tx.ut_valuta == "BTC"
        assert ks_tx.gebyr is None  # No separate fee in this trade
        assert ks_tx.gebyr_valuta is None
        assert "Swap from 2 txs" in ks_tx.notat

    def test_convert_eth_conversion_group(self, grouper: TransactionGrouper):
        """Test converting ETH Staking Shares to csETH trade group"""

        transactions = [
            CakeTransaction(
                date=datetime(2023, 2, 17, 17, 41, 22),
                operation="Converted ETH Staking Shares to csETH",
                amount=Decimal("-1.0"),  # Negative = outgoing ETH Staking Shares
                coin_asset="ETH",
                fiat_value=Decimal("1600.0"),
                fiat_currency="USD",
                transaction_id="conv1",
                withdrawal_address=None,
                reference="ref1",
                related_reference_id="conv-group-456",
            ),
            CakeTransaction(
                date=datetime(2023, 2, 17, 17, 41, 22),
                operation="Converted ETH Staking Shares to csETH",
                amount=Decimal("0.43287391"),  # Positive = incoming csETH
                coin_asset="csETH",
                fiat_value=Decimal("724.9096949939305"),
                fiat_currency="USD",
                transaction_id="conv2",
                withdrawal_address=None,
                reference="ref2",
                related_reference_id="conv-group-456",
            ),
        ]

        group = TransactionGroup(transactions, "swap", "conv-group-456")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Should be a complete conversion trade
        assert ks_tx.type == "Handel"
        assert ks_tx.inn == Decimal("0.43287391")  # csETH received
        assert ks_tx.inn_valuta == "csETH"
        assert ks_tx.ut == Decimal("1.0")  # ETH given up
        assert ks_tx.ut_valuta == "ETH"
        assert ks_tx.gebyr is None
        assert ks_tx.gebyr_valuta is None
        assert "Swap from 2 txs" in ks_tx.notat

    def test_convert_complex_trade_with_multiple_currencies(
        self, grouper: TransactionGrouper
    ):
        """Test trade group with multiple incoming and outgoing currencies"""

        transactions = [
            # Multiple incoming assets
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Buy token",
                amount=Decimal("10.0"),  # Positive DFI
                coin_asset="DFI",
                fiat_value=Decimal("30.0"),
                fiat_currency="USD",
                transaction_id="multi1",
                withdrawal_address=None,
                reference=None,
                related_reference_id="multi-trade",
            ),
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Buy token",
                amount=Decimal("5.0"),  # More positive DFI
                coin_asset="DFI",
                fiat_value=Decimal("15.0"),
                fiat_currency="USD",
                transaction_id="multi2",
                withdrawal_address=None,
                reference=None,
                related_reference_id="multi-trade",
            ),
            # Multiple outgoing assets
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Buy token",
                amount=Decimal("-0.1"),  # Negative ETH
                coin_asset="ETH",
                fiat_value=Decimal("300.0"),
                fiat_currency="USD",
                transaction_id="multi3",
                withdrawal_address=None,
                reference=None,
                related_reference_id="multi-trade",
            ),
            CakeTransaction(
                date=datetime(2022, 5, 15, 20, 1, 31),
                operation="Buy token",
                amount=Decimal("-0.05"),  # More negative ETH
                coin_asset="ETH",
                fiat_value=Decimal("150.0"),
                fiat_currency="USD",
                transaction_id="multi4",
                withdrawal_address=None,
                reference=None,
                related_reference_id="multi-trade",
            ),
        ]

        group = TransactionGroup(transactions, "swap", "multi-trade")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # Should aggregate properly
        assert ks_tx.type == "Handel"
        assert ks_tx.inn == Decimal("15.0")  # Sum of DFI (10 + 5)
        assert ks_tx.inn_valuta == "DFI"
        assert ks_tx.ut == Decimal("0.15")  # Sum of ETH (0.1 + 0.05)
        assert ks_tx.ut_valuta == "ETH"
        assert ks_tx.gebyr is None  # No fees in this scenario
        assert ks_tx.gebyr_valuta is None

    def test_convert_complex_same_currency_group_intelligent_resolution(
        self, grouper: TransactionGrouper
    ):
        """Test the complex case where same currency appears on both sides (like the csETH issue)"""

        # Simulate the problematic transaction group from the user's example
        transactions = [
            # Converted ETH Staking Shares to csETH (incoming csETH)
            CakeTransaction(
                date=datetime(2023, 2, 17, 17, 41, 22),
                operation="Converted ETH Staking Shares to csETH",
                amount=Decimal("0.43287391"),  # Positive csETH
                coin_asset="csETH",
                fiat_value=Decimal("724.91"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="ref1",
                related_reference_id="complex-group-789",
            ),
            # Deposit ETH (incoming ETH)
            CakeTransaction(
                date=datetime(2023, 2, 17, 18, 12, 42),
                operation="Deposit",
                amount=Decimal("0.40654695"),  # Positive ETH
                coin_asset="ETH",
                fiat_value=Decimal("682.55"),
                fiat_currency="USD",
                transaction_id="123",
                withdrawal_address=None,
                reference="ref2",
                related_reference_id="complex-group-789",
            ),
            # Withdrew for swap (outgoing csETH)
            CakeTransaction(
                date=datetime(2023, 2, 17, 18, 12, 43),
                operation="Withdrew for swap",
                amount=Decimal("-0.43070954045"),  # Negative csETH
                coin_asset="csETH",
                fiat_value=Decimal("-721.29"),
                fiat_currency="USD",
                transaction_id="123",
                withdrawal_address=None,
                reference="ref3",
                related_reference_id="complex-group-789",
            ),
            # Paid swap fee (outgoing csETH fee)
            CakeTransaction(
                date=datetime(2023, 2, 17, 18, 12, 43),
                operation="Paid swap fee",
                amount=Decimal("-0.00216436955"),  # Negative csETH
                coin_asset="csETH",
                fiat_value=Decimal("-3.62"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="ref4",
                related_reference_id="complex-group-789",
            ),
        ]

        group = TransactionGroup(transactions, "swap", "complex-group-789")
        kryptosekken_txs = grouper.convert_group_to_kryptosekken(group)

        assert len(kryptosekken_txs) == 1
        ks_tx = kryptosekken_txs[0]

        # This complex group correctly triggers Case B: conversion operation with net incoming asset
        # After netting, only ETH remains as incoming (csETH flows cancel out), plus conversion operation
        assert ks_tx.type == "Inntekt"
        assert ks_tx.inn == Decimal("0.40654695")  # ETH received (net incoming asset)
        assert ks_tx.inn_valuta == "ETH"
        assert ks_tx.ut is None  # No outflow for income
        assert ks_tx.ut_valuta is None
        assert ks_tx.gebyr is None
        assert ks_tx.gebyr_valuta is None

        # This is correctly treated as conversion income
        assert "ETH Staking Shares→csETH" in ks_tx.notat
        assert "NOK value:" in ks_tx.notat

    def test_time_based_group_splitting(self, grouper: TransactionGrouper):
        """Test that groups with large time gaps are split into separate groups"""

        # Create transactions with same reference_id but large time gap (31 minutes)
        transactions = [
            # First group: at 17:41 (converted transaction)
            CakeTransaction(
                date=datetime(2023, 2, 17, 17, 41, 22),
                operation="Deposit",  # Requires grouping
                amount=Decimal("0.5"),
                coin_asset="ETH",
                fiat_value=Decimal("1000.0"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="ref1",
                related_reference_id="time-split-test",
            ),
            # Second group: at 18:12 (31 minutes later - should be split)
            CakeTransaction(
                date=datetime(2023, 2, 17, 18, 12, 43),
                operation="Withdrew for swap",
                amount=Decimal("-0.43070954045"),
                coin_asset="csETH",
                fiat_value=Decimal("-721.29"),
                fiat_currency="USD",
                transaction_id="123",
                withdrawal_address=None,
                reference="ref2",
                related_reference_id="time-split-test",
            ),
            CakeTransaction(
                date=datetime(2023, 2, 17, 18, 12, 43),
                operation="Paid swap fee",
                amount=Decimal("-0.00216436955"),
                coin_asset="csETH",
                fiat_value=Decimal("-3.62"),
                fiat_currency="USD",
                transaction_id=None,
                withdrawal_address=None,
                reference="ref3",
                related_reference_id="time-split-test",
            ),
        ]

        # Group the transactions
        groups = grouper.group_transactions(transactions)

        # Should be split into separate groups due to time gap > 5 minutes
        swap_groups = [g for g in groups if g.group_type == "swap"]
        assert len(swap_groups) >= 2  # At least 2 separate groups

        # First group should have 1 transaction (the deposit)
        first_group = min(swap_groups, key=lambda g: g.timestamp)
        assert len(first_group.transactions) == 1
        assert first_group.transactions[0].operation == "Deposit"

        # Second group should have the swap transactions
        second_group = max(swap_groups, key=lambda g: g.timestamp)
        assert len(second_group.transactions) == 2
        operations = {tx.operation for tx in second_group.transactions}
        assert "Withdrew for swap" in operations
        assert "Paid swap fee" in operations
