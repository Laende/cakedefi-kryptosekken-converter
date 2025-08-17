import pytest

from src.operation_mapper import KryptosekkenTransactionType, OperationMapper


class TestOperationMapper:
    def test_staking_rewards_mapped_to_income(self):
        """Test that various staking rewards are mapped to income"""
        staking_operations = [
            "Staking reward",
            "Liquidity mining reward ETH-DFI",
            "Liquidity mining reward BTC-DFI",
            "Freezer staking bonus",
            "5 years freezer reward",
            "Earn reward",
            "YieldVault reward",
            "Referral reward",
        ]

        for operation in staking_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.INNTEKT
            assert OperationMapper.is_income_operation(
                operation, 10.0
            )  # Positive amount
            assert not OperationMapper.is_trade_operation(operation)

    def test_transfers_mapped_correctly(self):
        """Test that deposits and withdrawals are mapped correctly per Norwegian tax law"""
        # True transfers (same asset, no disposal)
        # Deposits are acquisitions (affect balance)
        deposit_operations = ["Deposit"]
        for operation in deposit_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert (
                tx_type == KryptosekkenTransactionType.ERVERV
            )  # Acquisition - affects balance

        # True transfers (same asset, no disposal, don't affect balance)
        transfer_in_operations = ["Exit staking wallet", "Adjusted Earn entry"]

        for operation in transfer_in_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.OVERFORING_INN

        # DeFi exits - correctly classified per Norwegian tax law
        # "Exited Earn" = disposing earn tokens for different assets = trade
        earn_exit_operations = ["Exited Earn"]
        for operation in earn_exit_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.HANDEL

        # "Exited YieldVault" = withdrawal of same asset from vault = transfer
        vault_exit_operations = ["Exited YieldVault"]
        for operation in vault_exit_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.OVERFORING_INN

        # Liquidity removals (disposing LP tokens) are now correctly classified as trades
        liquidity_removal_operations = [
            "Remove liquidity ETH-DFI",
            "Remove liquidity BTC-DFI",
            "Remove liquidity DUSD-DFI",
            "Removed liquidity",
        ]

        for operation in liquidity_removal_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.HANDEL

        assert (
            OperationMapper.get_transaction_type("Withdrawal")
            == KryptosekkenTransactionType.OVERFORING_UT
        )

    def test_fees_mapped_as_management_costs(self):
        """Test that fees are mapped as management costs"""
        fee_operations = ["Address creation fee", "Withdrawal fee"]

        for operation in fee_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.FORVALTNINGSKOSTNAD

    def test_defi_operations_mapped_as_trades(self):
        """Test that DeFi operations are correctly mapped as trades per Norwegian tax law"""
        # Liquidity provision operations (disposing assets to receive LP tokens) = trades
        liquidity_provision_operations = [
            "Add liquidity ETH-DFI",
            "Add liquidity BTC-DFI",
            "Add liquidity DUSD-DFI",
            "Added liquidity",
        ]

        for operation in liquidity_provision_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.HANDEL
            assert OperationMapper.is_trade_operation(operation)
            assert not OperationMapper.is_income_operation(operation, 10.0)

        # Vault/Earn entries - correctly classified per Norwegian tax law
        # "Entered Earn" = disposing asset for earn token = trade
        earn_enter_operations = ["Entered Earn"]
        for operation in earn_enter_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.HANDEL

        # "Entered YieldVault" = depositing asset to vault (same asset) = transfer out
        vault_enter_operations = ["Entered YieldVault"]
        for operation in vault_enter_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.OVERFORING_UT
            assert not OperationMapper.is_trade_operation(
                operation
            )  # Transfer, not trade
            assert not OperationMapper.is_income_operation(operation, 10.0)

    def test_eth_conversion_mapped_as_income(self):
        """Test that ETH staking conversion is correctly mapped as income per Norwegian tax law"""
        # Internal protocol conversions (ETH staking shares → csETH) are not taxable disposals
        # They represent receiving new assets from protocol rewards/conversions = income
        tx_type = OperationMapper.get_transaction_type(
            "Converted ETH Staking Shares to csETH"
        )
        assert tx_type == KryptosekkenTransactionType.INNTEKT
        assert not OperationMapper.is_trade_operation(
            "Converted ETH Staking Shares to csETH"
        )  # Income, not trade
        assert OperationMapper.is_income_operation(
            "Converted ETH Staking Shares to csETH"
        )
        assert OperationMapper.requires_grouping(
            "Converted ETH Staking Shares to csETH"
        )  # Still requires grouping

    def test_buy_token_mapped_as_income(self):
        """Test that Buy token is correctly mapped as income (not trade)"""
        tx_type = OperationMapper.get_transaction_type("Buy token")
        assert tx_type == KryptosekkenTransactionType.INNTEKT
        assert OperationMapper.is_income_operation("Buy token", 10.0)
        assert not OperationMapper.is_trade_operation("Buy token")
        assert not OperationMapper.requires_grouping("Buy token")

    def test_swap_components_mapped_safely(self):
        """Test that swap components have safe fallback mappings"""
        # Withdrew for swap should be transfer out
        tx_type = OperationMapper.get_transaction_type("Withdrew for swap")
        assert tx_type == KryptosekkenTransactionType.OVERFORING_UT
        assert not OperationMapper.is_trade_operation("Withdrew for swap")

        # Paid swap fee should be management cost
        tx_type = OperationMapper.get_transaction_type("Paid swap fee")
        assert tx_type == KryptosekkenTransactionType.FORVALTNINGSKOSTNAD
        assert not OperationMapper.is_trade_operation("Paid swap fee")

    def test_removed_liquidity_mapped_as_trade(self):
        """Test that liquidity removals are correctly mapped as trades per Norwegian tax law"""
        tx_type = OperationMapper.get_transaction_type("Removed liquidity")
        assert tx_type == KryptosekkenTransactionType.HANDEL
        assert OperationMapper.is_trade_operation("Removed liquidity")
        assert not OperationMapper.is_income_operation("Removed liquidity", 10.0)

    def test_grouping_operations_identified_correctly(self):
        """Test that operations requiring grouping are correctly identified"""
        grouping_operations = ["Withdrew for swap", "Paid swap fee", "Deposit"]

        for operation in grouping_operations:
            assert OperationMapper.requires_grouping(operation)

        non_grouping_operations = [
            "Staking reward",
            "Withdrawal",
            "Buy token",  # No longer requires grouping - it's income
        ]

        for operation in non_grouping_operations:
            assert not OperationMapper.requires_grouping(operation)

        # Conversion operations that DO require grouping (they may be part of larger trades)
        conversion_grouping_operations = [
            "Converted ETH Staking Shares to csETH"  # May be part of complex swap sequences
        ]

        for operation in conversion_grouping_operations:
            assert OperationMapper.requires_grouping(operation)

    def test_entry_staking_wallet_context_dependent(self):
        """Test that entry staking wallet depends on amount sign"""
        # Positive amount = income (reward)
        tx_type_positive = OperationMapper.get_transaction_type(
            "Entry staking wallet", amount=10.5
        )
        assert tx_type_positive == KryptosekkenTransactionType.INNTEKT

        # Negative amount = transfer out (deposit for staking)
        tx_type_negative = OperationMapper.get_transaction_type(
            "Entry staking wallet", amount=-5.2
        )
        assert tx_type_negative == KryptosekkenTransactionType.OVERFORING_UT

        # Default (no amount) = income
        tx_type_default = OperationMapper.get_transaction_type("Entry staking wallet")
        assert tx_type_default == KryptosekkenTransactionType.INNTEKT

    def test_entry_staking_wallet_special_cases(self):
        """Test special entry staking wallet operations"""
        special_operations = [
            "Entry staking wallet: Signup bonus",
            "Entry staking wallet: Referral signup bonus",
            "Entry staking wallet: Promotion bonus",
        ]

        for operation in special_operations:
            tx_type = OperationMapper.get_transaction_type(operation)
            assert tx_type == KryptosekkenTransactionType.INNTEKT

    def test_unknown_operation_raises_error(self):
        """Test that unknown operations raise ValueError"""
        with pytest.raises(ValueError, match="Unknown operation"):
            OperationMapper.get_transaction_type("Some unknown operation")

    def test_requires_grouping(self):
        """Test which operations require grouping"""
        grouping_operations = [
            "Withdrew for swap",
            "Paid swap fee",
            "Deposit",  # When part of swap
            "Add liquidity ETH-DFI",
            "Add liquidity BTC-DFI",
            "Add liquidity DUSD-DFI",
            "Add liquidity USDC-ETH",  # Test flexible pair support
            "Added liquidity",
            "Remove liquidity ETH-DFI",  # Liquidity removals require grouping
            "Remove liquidity BTC-DFI",  # Liquidity removals require grouping
            "Remove liquidity XYZ-ABC",  # Test flexible pair support
            "Removed liquidity",  # Result transactions require grouping
        ]

        non_grouping_operations = [
            "Staking reward",
            "Withdrawal",
            "Entered YieldVault",  # Individual trades, not grouped
            "Exited Earn",  # Individual trades, not grouped
        ]

        for operation in grouping_operations:
            assert OperationMapper.requires_grouping(operation)

        for operation in non_grouping_operations:
            assert not OperationMapper.requires_grouping(operation)
