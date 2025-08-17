from enum import Enum


class KryptosekkenTransactionType(Enum):
    """Valid transaction types for kryptosekken import"""

    HANDEL = "Handel"
    ERVERV = "Erverv"
    MINING = "Mining"
    INNTEKT = "Inntekt"
    TAP = "Tap"
    FORBRUK = "Forbruk"
    RENTEINNTEKT = "Renteinntekt"
    OVERFORING_INN = "Overføring-Inn"
    OVERFORING_UT = "Overføring-Ut"
    GAVE_INN = "Gave-Inn"
    GAVE_UT = "Gave-Ut"
    TAP_UTEN_FRADRAG = "Tap-uten-fradrag"
    FORVALTNINGSKOSTNAD = "Forvaltningskostnad"


class OperationMapper:
    """Maps CakeDeFi operations to kryptosekken transaction types"""

    # Main operation mapping
    OPERATION_MAPPING: dict[str, KryptosekkenTransactionType] = {
        # Income/Rewards → "Inntekt"
        "Staking reward": KryptosekkenTransactionType.INNTEKT,
        # Note: "Liquidity mining reward X-Y" patterns handled by pattern matching below
        "Freezer staking bonus": KryptosekkenTransactionType.INNTEKT,
        "5 years freezer reward": KryptosekkenTransactionType.INNTEKT,
        "Freezer liquidity mining bonus": KryptosekkenTransactionType.INNTEKT,
        "Earn reward": KryptosekkenTransactionType.INNTEKT,
        "YieldVault reward": KryptosekkenTransactionType.INNTEKT,
        "Referral reward": KryptosekkenTransactionType.INNTEKT,
        "Lending reward": KryptosekkenTransactionType.INNTEKT,
        "Promotion bonus": KryptosekkenTransactionType.INNTEKT,
        "Rewards from DeFiChain voting": KryptosekkenTransactionType.INNTEKT,
        # Entry staking wallet - context dependent
        "Entry staking wallet": KryptosekkenTransactionType.INNTEKT,  # Default, most are positive
        "Entry staking wallet: Signup bonus": KryptosekkenTransactionType.INNTEKT,
        "Entry staking wallet: Referral signup bonus": KryptosekkenTransactionType.INNTEKT,
        "Entry staking wallet: Promotion bonus": KryptosekkenTransactionType.INNTEKT,
        # Deposits are acquisitions (not transfers) - must affect balance in kryptosekken
        "Deposit": KryptosekkenTransactionType.ERVERV,  # Acquisition - affects balance
        "Withdrawal": KryptosekkenTransactionType.OVERFORING_UT,  # Transfer out - doesn't affect balance
        # Staking/Earn exits - review needed for tax classification
        "Exit staking wallet": KryptosekkenTransactionType.OVERFORING_INN,  # Simple staking withdrawal
        "Exited Earn": KryptosekkenTransactionType.HANDEL,  # If disposing of earn token, it's a trade
        "Exited YieldVault": KryptosekkenTransactionType.OVERFORING_INN,  # Withdrawal from vault (same asset)
        "Adjusted Earn entry": KryptosekkenTransactionType.OVERFORING_INN,
        # Liquidity removals - properly classified as trades (Handel) for Norwegian tax law
        # Removing liquidity: disposing of LP token to receive two assets = trade
        # NOTE: Specific pairs like "Remove liquidity ETH-DFI" are handled by pattern matching in requires_grouping()
        "Removed liquidity": KryptosekkenTransactionType.HANDEL,  # Generic LP token disposal
        # Fees and costs
        "Address creation fee": KryptosekkenTransactionType.FORVALTNINGSKOSTNAD,
        "Withdrawal fee": KryptosekkenTransactionType.FORVALTNINGSKOSTNAD,
        # DeFi operations - properly classified as trades (Handel) for Norwegian tax law
        # Adding liquidity: disposing of two assets (ETH+DFI) to receive LP token = trade
        # NOTE: Specific pairs like "Add liquidity ETH-DFI" are handled by pattern matching in requires_grouping()
        "Added liquidity": KryptosekkenTransactionType.HANDEL,  # Receipt of LP token part of trade
        # Vault/Earn operations - internal movements for same asset vaults
        # Note: These represent depositing funds into yield-generating pools
        # For Norwegian tax: treated as transfers since you get the same asset back
        "Entered YieldVault": KryptosekkenTransactionType.OVERFORING_UT,  # Deposit to vault
        "Entered Earn": KryptosekkenTransactionType.HANDEL,  # Keep as trade if receiving different token
        # Swaps (will be grouped together)
        "Withdrew for swap": KryptosekkenTransactionType.OVERFORING_UT,
        "Paid swap fee": KryptosekkenTransactionType.FORVALTNINGSKOSTNAD,  # Fee part of trade
        # Yield Vault operations
        # Conversions - properly classified as trades (Handel) for Norwegian tax law
        # Converting one token type to another = disposing of one asset to receive another = trade
        "Converted ETH Staking Shares to csETH": KryptosekkenTransactionType.INNTEKT,
        # Token operations
        "Buy token": KryptosekkenTransactionType.INNTEKT,
    }

    # Special operations that need context-dependent handling
    CONTEXT_DEPENDENT_OPERATIONS = {
        "Entry staking wallet",  # Can be positive (income) or negative (trade)
        "Deposit",  # Can be transfer or part of swap
    }

    @classmethod
    def get_transaction_type(
        cls, operation: str, amount: float | None = None
    ) -> KryptosekkenTransactionType:
        """
        Get the kryptosekken transaction type for a CakeDeFi operation.

        Args:
            operation: The CakeDeFi operation string
            amount: The transaction amount (used for context-dependent operations)

        Returns:
            The corresponding kryptosekken transaction type

        Raises:
            ValueError: If the operation is not recognized
        """
        # Handle the special case for "Entry staking wallet" FIRST
        if operation == "Entry staking wallet" and amount is not None:
            if amount < 0:
                # Negative "Entry staking wallet" transactions create phantom outflows
                # These represent moving funds INTO staking pools - not a taxable disposal for Norwegian tax
                # Solution: Skip these transactions entirely in the processing pipeline
                # They will be filtered out before creating kryptosekken transactions
                return (
                    KryptosekkenTransactionType.OVERFORING_UT
                )  # Temporary - will be filtered
            else:
                # Positive amounts are bonuses/income.
                return KryptosekkenTransactionType.INNTEKT

        # Check static mapping first
        if operation in cls.OPERATION_MAPPING:
            return cls.OPERATION_MAPPING[operation]

        # Handle dynamic pattern matching for liquidity operations
        if operation.startswith("Add liquidity ") or operation.startswith(
            "Remove liquidity "
        ):
            return KryptosekkenTransactionType.HANDEL

        # Handle dynamic pattern matching for liquidity mining rewards
        if operation.startswith("Liquidity mining reward "):
            return KryptosekkenTransactionType.INNTEKT

        # Fallback for unrecognized operations
        raise ValueError(f"Unknown operation: {operation}")

    @classmethod
    def is_income_operation(cls, operation: str, amount: float | None = None) -> bool:
        """Check if an operation represents taxable income"""
        try:
            tx_type = cls.get_transaction_type(operation, amount)
            return tx_type == KryptosekkenTransactionType.INNTEKT
        except ValueError:
            return False

    @classmethod
    def is_trade_operation(cls, operation: str) -> bool:
        """Check if an operation represents a trade/taxable event"""
        try:
            tx_type = cls.get_transaction_type(operation)
            return tx_type == KryptosekkenTransactionType.HANDEL
        except ValueError:
            return False

    @classmethod
    def should_skip_transaction(
        cls, operation: str, amount: float | None = None
    ) -> bool:
        """
        Check if a transaction should be skipped entirely for tax purposes.

        Norwegian tax law: Moving funds into/out of staking pools is not a taxable event.
        These are internal transfers of the same assets and should not appear in tax reports.
        """
        # Skip negative "Entry staking wallet" - internal movements into staking
        if operation == "Entry staking wallet" and amount is not None and amount < 0:
            return True

        # Note: "Exit staking wallet" is NOT skipped because it represents funds returning
        # from staking pools, which should be tracked for tax purposes

        return False

    @classmethod
    def requires_grouping(cls, operation: str) -> bool:
        """Check if operation is part of multi-transaction group (like swaps)"""
        # Static operations that require grouping
        static_operations = [
            # --- Existing swap operations ---
            "Withdrew for swap",
            "Paid swap fee",
            "Deposit",  # When part of swap group
            # --- Liquidity result operations ---
            "Added liquidity",  # Receipt of LP token
            "Removed liquidity",  # Spending of LP token
            # --- Conversion operations ---
            "Converted ETH Staking Shares to csETH",  # Conversion that's part of larger trade
        ]

        if operation in static_operations:
            return True

        # Dynamic pattern matching for liquidity operations
        # Supports any pair like ETH-DFI, BTC-DFI, USDC-ETH, etc.
        return operation.startswith("Add liquidity ") or operation.startswith(
            "Remove liquidity "
        )
