"""
Balance Tracker for Multi-Year Cryptocurrency Tax Validation

This module tracks cryptocurrency balances across tax years to enable accurate
validation of yearly transaction data. It maintains a running balance of all
assets, ensuring that spending in a given year does not exceed the holdings
carried over from previous years, a key requirement for economic validity in
tax reporting (e.g., for Norwegian compliance).
"""

from collections import defaultdict
from collections.abc import Generator
from decimal import Decimal
import json
import logging
from pathlib import Path
from typing import Any, TypeAlias

from .constants import DEFAULT_BALANCE_FILE, NEGLIGIBLE_AMOUNT


# Define a clear type for tx dictionaries
Transaction: TypeAlias = dict[str, Any]

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class BalanceTracker:
    """
    Tracks cryptocurrency balances across multiple tax years by processing
    transaction lists and persisting the year-end state.

    Attributes:
        balance_file (Path): Path to the JSON file for storing balance history.
        balance_history (Dict[int, Dict[str, Decimal]]): A nested dictionary
            storing the ending balance of each currency for each year.
            Example: {2023: {'BTC': Decimal('1.5'), 'ETH': Decimal('10.0')}}
    """

    def __init__(self, balance_file: Path | None = None):
        """
        Initializes the BalanceTracker, loading any existing state from disk.

        Args:
            balance_file:
                Optional path to the JSON file for storing balance state.
                Defaults to 'balance_state.json'.
        """
        self.balance_file = balance_file or DEFAULT_BALANCE_FILE
        self.balance_history: dict[int, dict[str, Decimal]] = self._load_balance_state()

    def _load_balance_state(self) -> dict[int, dict[str, Decimal]]:
        """Load balance history from JSON file."""

        if not self.balance_file.exists():
            logging.info(
                "No existing balance file found at %s, starting fresh.",
                self.balance_file,
            )
            return {}

        try:
            with open(self.balance_file) as f:
                raw_data = json.load(f)
                history = {
                    int(year): {
                        currency: Decimal(amount)
                        for currency, amount in balances.items()
                    }
                    for year, balances in raw_data.items()
                }

            years = sorted(history.keys())
            logging.info("📊 Loaded balance history for years: %s", years)
            return history
        except (OSError, json.JSONDecodeError) as e:
            logging.error(
                "⚠️ Could not load balance state from %s: %s", self.balance_file, e
            )
            return {}

    def save_balance_state(self):
        """Save balance history to JSON file."""
        try:
            # Prepare data for serialization
            serializable_history = {
                str(year): {
                    currency: str(amount)
                    for currency, amount in balances.items()
                    if not self._is_negligible(
                        amount
                    )  # Save non-negligible balances only
                }
                for year, balances in self.balance_history.items()
            }

            with self.balance_file.open("w") as f:
                json.dump(serializable_history, f, indent=2)
            logging.info("💾 Saved balance state to %s", self.balance_file)
        except OSError as e:
            logging.error(
                "⚠️ Could not save balance state to %s: %s", self.balance_file, e
            )

    def get_starting_balances(self, year: int) -> dict[str, Decimal]:
        """Get starting balances for year (previous year's ending balances)."""
        previous_year = year - 1

        if previous_year in self.balance_history:
            return self.balance_history[previous_year].copy()

        logging.info(
            "📊 No data for %d; starting year %d with zero balances.",
            previous_year,
            year,
        )
        return {}

    @staticmethod
    def _is_negligible(amount: Decimal) -> bool:
        """Check if amount is negligible (close to zero)."""
        return abs(amount) < NEGLIGIBLE_AMOUNT

    @staticmethod
    def _get_transaction_deltas(
        tx: Transaction,
    ) -> Generator[tuple[str, Decimal, bool, str], None, None]:
        """Generate balance changes from transaction (outflows first)."""

        # Handle dict and KryptosekkenTransaction objects
        def get_field(field):
            if hasattr(tx, field):
                return getattr(tx, field, None)
            else:
                return tx.get(field)

        # Yield outflows first (spending/fees) for correct validation
        if (ut_amount := get_field("ut")) and (ut_currency := get_field("ut_valuta")):
            yield ut_currency, ut_amount, True, "outflow"
        if (fee_amount := get_field("gebyr")) and (
            fee_currency := get_field("gebyr_valuta")
        ):
            yield fee_currency, fee_amount, True, "fee"

        # Yield inflows last (receiving)
        if (in_amount := get_field("inn")) and (in_currency := get_field("inn_valuta")):
            yield in_currency, in_amount, False, "inflow"

    def process_and_validate_year(
        self, year: int, transactions: list[Transaction]
    ) -> dict:
        """
        Processes and validates a year's transactions against starting balances.

        This is the primary method for yearly processing. It performs two key tasks:
        1.  Validates that no transaction attempts to spend more than the available balance.
        2.  Calculates the final year-end balances and stores them in the history.

        Returns:
            A dictionary containing the validation result and balance information.
        """
        starting_balances = self.get_starting_balances(year)
        running_balances = defaultdict(Decimal, starting_balances)
        problematic_txs = []

        for tx in transactions:
            for currency, amount, is_outflow, desc in self._get_transaction_deltas(tx):
                if is_outflow:
                    # Validate if there is enough balance before debiting
                    if running_balances[currency] < amount:
                        row_num = (
                            getattr(tx, "row_num", None)
                            if hasattr(tx, "row_num")
                            else tx.get("row")
                        )
                        tx_type = (
                            getattr(tx, "type", None)
                            if hasattr(tx, "type")
                            else tx.get("type")
                        )

                        problematic_txs.append(
                            {
                                "row": row_num,
                                "currency": currency,
                                "attempted": amount,
                                "available": running_balances[currency],
                                "deficit": amount - running_balances[currency],
                                "transaction": f"Row {row_num or '?'}: {tx_type or '?'} ({desc})",
                            }
                        )
                    running_balances[currency] -= amount
                else:  # is inflow
                    running_balances[currency] += amount

        # Create final balances, filtering out any negligible amounts
        final_balances = {
            currency: balance
            for currency, balance in running_balances.items()
            if not self._is_negligible(balance)
        }

        # Store the calculated balances in history for the next year
        self.balance_history[year] = final_balances

        # Prepare Validation Report
        errors = []
        if problematic_txs:
            errors.append(
                f"❌ Found {len(problematic_txs)} transactions with insufficient funds:"
            )
            # Report the top 5 most significant deficits first
            sorted_problems = sorted(
                problematic_txs, key=lambda p: p["deficit"], reverse=True
            )
            for prob in sorted_problems[:5]:
                errors.append(
                    f"  {prob['transaction']}: tried to spend {prob['attempted']:.8f} {prob['currency']}, "
                    f"but only {prob['available']:.8f} was available."
                )
            if len(sorted_problems) > 5:
                errors.append(f"  ... and {len(sorted_problems) - 5} more.")

        info = (
            [f"✅ All {year} transactions respect multi-year balance constraints."]
            if not errors
            else []
        )

        return {
            "valid": not errors,
            "errors": errors,
            "info": info,
            "starting_balances": starting_balances,
            "ending_balances": final_balances,
            "problematic_transactions": problematic_txs,
        }

    def generate_balance_report(self) -> str:
        """Generates a comprehensive, formatted string report of all tracked balances."""
        if not self.balance_history:
            return "No balance history available."

        years = sorted(self.balance_history.keys())
        all_currencies = sorted(
            {
                currency
                for year_balances in self.balance_history.values()
                for currency in year_balances
            }
        )

        header = f"""
============================================================
        MULTI-YEAR BALANCE TRACKING REPORT
        Covering {len(years)} years: {min(years)}-{max(years)}
        Total currencies tracked: {len(all_currencies)}
============================================================
"""
        report_lines = [header.strip()]

        for currency in all_currencies:
            report_lines.append(f"\n--- {currency} ---")
            for year in years:
                balance = self.balance_history[year].get(currency, Decimal("0"))
                if not self._is_negligible(balance):
                    report_lines.append(f"  {year} Year-End: {balance:18.8f}")

        return "\n".join(report_lines)
