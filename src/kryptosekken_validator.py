"""
Kryptosekken CSV Validator

A comprehensive tool for validating Kryptosekken CSV files against official
specifications, economic logic, and Norwegian tax compliance rules.
"""

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from .constants import (
    BALANCE_TOLERANCE,
    CSV_HEADERS,
    CURRENCY_CODE_PATTERN,
    DUST_THRESHOLD,
    HIGH_FEE_PERCENTAGE_THRESHOLD,
    SUPPORTED_TIMESTAMP_FORMATS,
    VALID_TRANSACTION_TYPES,
    is_valid_currency_code,
    is_valid_decimal_precision,
)

# Import models and constants
from .models import Transaction


# --- Structured Validation Issue ---
ValidationIssueLevel = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class ValidationIssue:
    """A structured representation of a validation finding."""

    level: ValidationIssueLevel
    message: str
    row_num: int | None = None  # CSV row number (2-indexed)


class KryptosekkenValidator:
    """
    Validates Kryptosekken CSV files for structural integrity, logical
    consistency, and compliance with official standards.

    The validator is stateless; each call to `validate_csv_file` is independent.
    """

    def __init__(self):
        self.issues: list[ValidationIssue] = []
        # Legacy fields for backward compatibility during transition
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.info: list[str] = []

    def _add_issue(
        self, level: ValidationIssueLevel, message: str, row_num: int | None = None
    ):
        """Helper to add a structured validation issue to the current run's results."""
        self.issues.append(ValidationIssue(level, message, row_num))

    def validate_csv_file(
        self,
        csv_file: Path,
        expected_year: int | None = None,
        export_problematic: bool = True,
    ) -> dict:
        """
        Validates a single Kryptosekken CSV file.

        Args:
            csv_file: Path to the CSV file.
            expected_year: The tax year all transactions are expected to be in.
            export_problematic: If True, exports problematic transactions to
                                separate files for easier debugging.

        Returns:
            A dictionary summarizing the validation results.
        """
        self.issues.clear()  # Reset issues for each validation run

        if not csv_file.exists():
            self._add_issue("error", f"File not found: {csv_file}")
            return self._build_result()

        try:
            transactions = self._load_transactions(csv_file)

            # If loading failed or file is empty, return early.
            if not transactions:
                if not any(issue.level == "error" for issue in self.issues):
                    self._add_issue(
                        "warning", "CSV file is empty or contains only a header."
                    )
                return self._build_result()

            # Run all validations
            self._validate_structure_and_fields(transactions)
            self._validate_dates(transactions, expected_year)
            self._validate_transaction_logic(transactions)
            self._validate_official_field_requirements(transactions)
            self._validate_currency_balances(transactions)
            self._validate_norwegian_tax_compliance(transactions)
            self._validate_economic_reasonableness(transactions)

            result = self._build_result(transactions)

            # Export problematic transactions if validation failed and export is enabled
            if not result["valid"] and export_problematic and expected_year:
                self._export_problematic_transactions(
                    csv_file, transactions, expected_year
                )

            return result

        except Exception as e:
            self._add_issue("error", f"Failed to validate file: {str(e)}")
            return self._build_result()

    def _load_transactions(self, csv_file: Path) -> list[Transaction]:
        """Load transactions from CSV file"""
        transactions = []

        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Verify headers
            if reader.fieldnames != CSV_HEADERS:
                self._add_issue(
                    "error",
                    f"Invalid CSV headers. Expected: {CSV_HEADERS}, Got: {reader.fieldnames}",
                )
                return []

            for row_num, row in enumerate(reader, start=2):
                try:
                    # Parse amounts with validation
                    inn = (
                        self._parse_decimal(row["Inn"], "Inn", row_num)
                        if row["Inn"]
                        else None
                    )
                    ut = (
                        self._parse_decimal(row["Ut"], "Ut", row_num)
                        if row["Ut"]
                        else None
                    )
                    gebyr = (
                        self._parse_decimal(row["Gebyr"], "Gebyr", row_num)
                        if row["Gebyr"]
                        else None
                    )

                    # Parse timestamp
                    tidspunkt = (
                        self._parse_timestamp(row["Tidspunkt"], row_num)
                        if row["Tidspunkt"]
                        else None
                    )

                    transaction = Transaction.for_validation(
                        row_num=row_num,
                        tidspunkt=tidspunkt,
                        type=row["Type"],
                        inn=inn,
                        inn_valuta=row["Inn-Valuta"] if row["Inn-Valuta"] else None,
                        ut=ut,
                        ut_valuta=row["Ut-Valuta"] if row["Ut-Valuta"] else None,
                        gebyr=gebyr,
                        gebyr_valuta=row["Gebyr-Valuta"]
                        if row["Gebyr-Valuta"]
                        else None,
                        marked=row["Marked"] if row["Marked"] else None,
                        notat=row["Notat"] if row["Notat"] else None,
                    )
                    transactions.append(transaction)

                except Exception as e:
                    self._add_issue(
                        "error",
                        f"Row {row_num}: Failed to parse transaction - {str(e)}",
                    )

        return transactions

    def _parse_decimal(
        self, value: str, field_name: str, row_num: int
    ) -> Decimal | None:
        """Parse decimal value according to kryptosekken specifications"""
        try:
            decimal_val = Decimal(value)

            # Check precision limits (max 18 digits integer + 18 decimals)
            if not is_valid_decimal_precision(decimal_val):
                self._add_issue(
                    "error",
                    f"{field_name} exceeds precision limits (max 18 digits + 18 decimals): {value}",
                    row_num,
                )
                return None

            return decimal_val
        except Exception:
            self._add_issue(
                "error", f"Invalid {field_name} decimal format: {value}", row_num
            )
            return None

    def _parse_timestamp(self, value: str, row_num: int) -> datetime | None:
        """Parse timestamp according to kryptosekken specifications"""
        for fmt in SUPPORTED_TIMESTAMP_FORMATS:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue

        self._add_issue("error", f"Invalid Tidspunkt format: {value}", row_num)
        return None

    def _validate_structure_and_fields(self, transactions: list[Transaction]):
        """Validates fundamental row structure and official field requirements."""
        for tx in transactions:
            if not tx.tidspunkt:
                self._add_issue("error", "Tidspunkt is a required field.", tx.row_num)
            if not tx.type:
                self._add_issue("error", "Type is a required field.", tx.row_num)
            elif tx.type not in VALID_TRANSACTION_TYPES:
                self._add_issue("error", f"Invalid Type '{tx.type}'.", tx.row_num)

            if tx.inn is None and tx.ut is None:
                self._add_issue(
                    "error",
                    "Transaction must have an 'Inn' or 'Ut' amount.",
                    tx.row_num,
                )
            if tx.inn is not None and not tx.inn_valuta:
                self._add_issue(
                    "error",
                    "Inn amount is present but Inn-Valuta is missing.",
                    tx.row_num,
                )
            if tx.ut is not None and not tx.ut_valuta:
                self._add_issue(
                    "error",
                    "Ut amount is present but Ut-Valuta is missing.",
                    tx.row_num,
                )
            if tx.gebyr is not None and not tx.gebyr_valuta:
                self._add_issue(
                    "error",
                    "Gebyr amount is present but Gebyr-Valuta is missing.",
                    tx.row_num,
                )

            for code, name in [
                (tx.inn_valuta, "Inn-Valuta"),
                (tx.ut_valuta, "Ut-Valuta"),
                (tx.gebyr_valuta, "Gebyr-Valuta"),
            ]:
                if code and not CURRENCY_CODE_PATTERN.match(code):
                    self._add_issue(
                        "error", f"Invalid {name} format: '{code}'.", tx.row_num
                    )

    def _validate_official_field_requirements(self, transactions: list[Transaction]):
        """Validate according to official kryptosekken field requirements"""
        for tx in transactions:
            # REQUIRED FIELDS (not marked as "Kan være tomt" in documentation)

            # Tidspunkt: Required
            if not tx.tidspunkt:
                self._add_issue("error", "Tidspunkt is required", tx.row_num)

            # Type: Required and must be valid
            if not tx.type:
                self._add_issue("error", "Type is required", tx.row_num)
            elif tx.type not in VALID_TRANSACTION_TYPES:
                self._add_issue(
                    "error",
                    f"Invalid Type '{tx.type}'. Must be one of: {', '.join(sorted(VALID_TRANSACTION_TYPES))}",
                    tx.row_num,
                )

            # CURRENCY CODE VALIDATION (1-16 chars: A-Z, 0-9, bindestrek)
            for field, field_name in [
                (tx.inn_valuta, "Inn-Valuta"),
                (tx.ut_valuta, "Ut-Valuta"),
                (tx.gebyr_valuta, "Gebyr-Valuta"),
            ]:
                if field is not None and not is_valid_currency_code(field):
                    self._add_issue(
                        "error",
                        f"Invalid {field_name} '{field}' (must be 1-16 chars: A-Z, 0-9, bindestrek)",
                        tx.row_num,
                    )

    def _validate_dates(
        self, transactions: list[Transaction], expected_year: int | None
    ):
        """Validates transaction dates for consistency."""
        dates = [tx.tidspunkt for tx in transactions if tx.tidspunkt]
        if not dates:
            return

        if expected_year:
            wrong_year_rows = [
                tx.row_num
                for tx in transactions
                if tx.tidspunkt and tx.tidspunkt.year != expected_year
            ]
            if wrong_year_rows:
                self._add_issue(
                    "error",
                    f"{len(wrong_year_rows)} transactions are not from expected year {expected_year}.",
                    wrong_year_rows[0],
                )

        min_date, max_date = min(dates), max(dates)
        date_span_days = (max_date - min_date).days
        self._add_issue(
            "info",
            f"Transaction date range: {min_date.date()} to {max_date.date()} ({date_span_days} days).",
        )
        if date_span_days > 370:
            self._add_issue(
                "warning",
                f"Transactions span {date_span_days} days, which is more than a typical tax year.",
            )

    def _validate_currency_balances(self, transactions: list[Transaction]):
        """Validate that no currency has negative net balance"""
        currency_balances = defaultdict(Decimal)
        currency_transactions = defaultdict(list)

        for tx in transactions:
            # Track incoming amounts with metadata
            if tx.inn is not None and tx.inn_valuta:
                currency_balances[tx.inn_valuta] += tx.inn
                currency_transactions[tx.inn_valuta].append(
                    (tx.row_num, "Inn", tx.inn, tx.tidspunkt, tx.type, tx.notat or "")
                )

            # Track outgoing amounts with metadata
            if tx.ut is not None and tx.ut_valuta:
                currency_balances[tx.ut_valuta] -= tx.ut
                currency_transactions[tx.ut_valuta].append(
                    (tx.row_num, "Ut", -tx.ut, tx.tidspunkt, tx.type, tx.notat or "")
                )

            # Track fees with metadata
            if tx.gebyr is not None and tx.gebyr_valuta:
                currency_balances[tx.gebyr_valuta] -= tx.gebyr
                currency_transactions[tx.gebyr_valuta].append(
                    (
                        tx.row_num,
                        "Gebyr",
                        -tx.gebyr,
                        tx.tidspunkt,
                        tx.type,
                        tx.notat or "",
                    )
                )

        # Check for negative balances
        negative_balances = []
        negative_lp_tokens = []

        for currency, balance in currency_balances.items():
            if balance < -BALANCE_TOLERANCE:
                # Separate LP tokens from regular currencies
                # LP tokens typically have hyphen in name (e.g., BTC-DFI, ETH-DFI)
                if "-" in currency and currency not in [
                    "NOK",
                    "USD",
                    "EUR",
                ]:  # LP token
                    negative_lp_tokens.append((currency, balance))
                else:
                    negative_balances.append((currency, balance))

        if negative_balances:
            self._add_issue(
                "error",
                "❌ Negative currency balances detected (impossible - you can't spend more than you have):",
            )
            for currency, balance in negative_balances:
                # Show summary - detailed transactions will be in exported files
                total_txs = len(currency_transactions[currency])
                total_in = sum(
                    amount
                    for row, tx_type, amount, timestamp, tx_category, note in currency_transactions[
                        currency
                    ]
                    if amount > 0
                )
                total_out = abs(
                    sum(
                        amount
                        for row, tx_type, amount, timestamp, tx_category, note in currency_transactions[
                            currency
                        ]
                        if amount < 0
                    )
                )

                self._add_issue(
                    "error",
                    f"{currency}: {balance:.8f} ({total_txs} transactions: +{total_in:.8f} in, -{total_out:.8f} out, rows: {[tx[0] for tx in currency_transactions[currency][:5]]})",
                )

        # Handle LP token negative balances as warnings (expected for multi-year portfolios)
        if negative_lp_tokens:
            self._add_issue(
                "warning",
                "⚠️  LP token negative balances (likely acquired in previous years):",
            )
            for currency, balance in negative_lp_tokens:
                self._add_issue(
                    "warning",
                    f"{currency}: {balance:.8f} (LP tokens from previous tax years)",
                )

        if not negative_balances:
            if negative_lp_tokens:
                self._add_issue(
                    "info",
                    "✅ All regular currencies have non-negative balances (LP token negatives are expected)",
                )
            else:
                self._add_issue(
                    "info", "✅ All currencies have non-negative net balances"
                )

        # Summary of currency flows
        self._add_issue("info", "Currency balance summary:")
        for currency, balance in sorted(currency_balances.items()):
            status = "✅" if balance >= -BALANCE_TOLERANCE else "❌"
            self._add_issue("info", f"  {status} {currency}: {balance:>15.8f}")

    def _validate_transaction_logic(self, transactions: list[Transaction]):
        """Validate transaction business logic"""
        type_counts = defaultdict(int)
        suspicious_trades = []

        for tx in transactions:
            type_counts[tx.type] += 1

            # Validate trade transactions
            if tx.type == "Handel":
                # Trades should have both Inn and Ut
                if tx.inn is None or tx.ut is None:
                    time_str = (
                        tx.tidspunkt.strftime("%Y-%m-%d %H:%M:%S")
                        if tx.tidspunkt
                        else "No timestamp"
                    )
                    note_preview = (
                        (tx.notat or "")[:60] + "..."
                        if len(tx.notat or "") > 60
                        else (tx.notat or "")
                    )
                    self._add_issue(
                        "error",
                        f"Handel transaction missing Inn or Ut | {time_str} | Inn: {tx.inn} {tx.inn_valuta or ''} | Ut: {tx.ut} {tx.ut_valuta or ''} | Note: {note_preview}",
                        tx.row_num,
                    )

                # Currencies should be different for trades
                if tx.inn_valuta and tx.ut_valuta and tx.inn_valuta == tx.ut_valuta:
                    time_str = (
                        tx.tidspunkt.strftime("%Y-%m-%d %H:%M:%S")
                        if tx.tidspunkt
                        else "No timestamp"
                    )
                    self._add_issue(
                        "error",
                        f"Handel with same Inn-Valuta and Ut-Valuta ({tx.inn_valuta}) | {time_str}",
                        tx.row_num,
                    )

                # Check for suspicious trade ratios
                if tx.inn and tx.ut:
                    ratio = abs(tx.inn / tx.ut)
                    if ratio > 1000000 or ratio < 0.000001:
                        suspicious_trades.append(
                            (tx.row_num, tx.inn_valuta, tx.ut_valuta, ratio)
                        )

            # Validate income transactions
            elif tx.type == "Inntekt":
                # Income should have Inn
                if tx.inn is None:
                    time_str = (
                        tx.tidspunkt.strftime("%Y-%m-%d %H:%M:%S")
                        if tx.tidspunkt
                        else "No timestamp"
                    )
                    note_preview = (
                        (tx.notat or "")[:60] + "..."
                        if len(tx.notat or "") > 60
                        else (tx.notat or "")
                    )
                    self._add_issue(
                        "error",
                        f"Inntekt transaction missing Inn | {time_str} | Note: {note_preview}",
                        tx.row_num,
                    )

                # Income should be positive
                if tx.inn and tx.inn <= 0:
                    time_str = (
                        tx.tidspunkt.strftime("%Y-%m-%d %H:%M:%S")
                        if tx.tidspunkt
                        else "No timestamp"
                    )
                    self._add_issue(
                        "error",
                        f"Inntekt with non-positive amount: {tx.inn} | {time_str}",
                        tx.row_num,
                    )

            # Validate transfer transactions
            elif tx.type in ["Overføring-Inn", "Overføring-Ut"]:
                # Transfers should have either Inn or Ut, but not both
                if tx.type == "Overføring-Inn" and tx.inn is None:
                    time_str = (
                        tx.tidspunkt.strftime("%Y-%m-%d %H:%M:%S")
                        if tx.tidspunkt
                        else "No timestamp"
                    )
                    note_preview = (
                        (tx.notat or "")[:60] + "..."
                        if len(tx.notat or "") > 60
                        else (tx.notat or "")
                    )
                    self._add_issue(
                        "error",
                        f"Overføring-Inn missing Inn | {time_str} | Note: {note_preview}",
                        tx.row_num,
                    )

                if tx.type == "Overføring-Ut" and tx.ut is None:
                    time_str = (
                        tx.tidspunkt.strftime("%Y-%m-%d %H:%M:%S")
                        if tx.tidspunkt
                        else "No timestamp"
                    )
                    note_preview = (
                        (tx.notat or "")[:60] + "..."
                        if len(tx.notat or "") > 60
                        else (tx.notat or "")
                    )
                    self._add_issue(
                        "error",
                        f"Overføring-Ut missing Ut | {time_str} | Note: {note_preview}",
                        tx.row_num,
                    )

        # Report suspicious trades
        if suspicious_trades:
            self._add_issue(
                "warning", f"Found {len(suspicious_trades)} suspicious trade ratios:"
            )
            for row, inn_valuta, ut_valuta, ratio in suspicious_trades[:5]:
                self._add_issue(
                    "warning",
                    f"  Row {row}: {inn_valuta}/{ut_valuta} ratio = {ratio:.2e}",
                )

        # Report transaction type summary
        self._add_issue("info", "Transaction types:")
        for tx_type, count in sorted(type_counts.items()):
            self._add_issue("info", f"  {tx_type}: {count:,}")

    def _validate_norwegian_tax_compliance(self, transactions: list[Transaction]):
        """Validate Norwegian tax compliance requirements"""

        # Count tax-relevant transactions
        income_count = sum(1 for tx in transactions if tx.type == "Inntekt")
        trade_count = sum(1 for tx in transactions if tx.type == "Handel")

        self._add_issue("info", "Norwegian tax summary:")
        self._add_issue("info", f"  Income transactions (Inntekt): {income_count:,}")
        self._add_issue("info", f"  Taxable trades (Handel): {trade_count:,}")

        # Check for missing NOK valuations in income (now in note field)
        income_without_nok = 0
        for tx in transactions:
            if tx.type == "Inntekt":
                # Income should have NOK valuation in note field (new format)
                # Since we moved NOK values to notes, check if note contains "NOK value:"
                if not tx.notat or "NOK value:" not in tx.notat:
                    income_without_nok += 1

        if income_without_nok > 0:
            self._add_issue(
                "warning",
                f"{income_without_nok} income transactions without NOK valuation in notes",
            )

        # Validate that we have reasonable amounts for Norwegian context
        large_trades = []
        for tx in transactions:
            if tx.type == "Handel" and tx.ut and tx.ut_valuta == "NOK":
                # Trades valued over 1 million NOK might need extra attention
                if tx.ut > 1000000:
                    large_trades.append((tx.row_num, tx.ut))

        if large_trades:
            self._add_issue("info", f"Large trades (>1M NOK): {len(large_trades)}")
            for row, amount in large_trades[:3]:
                self._add_issue("info", f"  Row {row}: {amount:,.0f} NOK")

    def _validate_economic_reasonableness(self, transactions: list[Transaction]):
        """Validate economic reasonableness of transactions"""

        # Check for zero amounts
        zero_amounts = []
        for tx in transactions:
            if (
                (tx.inn is not None and tx.inn == 0)
                or (tx.ut is not None and tx.ut == 0)
                or (tx.gebyr is not None and tx.gebyr == 0)
            ):
                zero_amounts.append(tx.row_num)

        if zero_amounts:
            self._add_issue(
                "warning",
                f"Found {len(zero_amounts)} transactions with zero amounts (rows: {zero_amounts[:10]})",
            )

        # Check for very small amounts (potential rounding/dust issues)
        dust_transactions = []

        for tx in transactions:
            amounts = [tx.inn, tx.ut, tx.gebyr]
            for amount in amounts:
                if amount is not None and 0 < abs(amount) < DUST_THRESHOLD:
                    dust_transactions.append((tx.row_num, amount))
                    break

        if dust_transactions:
            self._add_issue(
                "info",
                f"Found {len(dust_transactions)} very small amount transactions (< {DUST_THRESHOLD})",
            )
            for row, amount in dust_transactions[:5]:
                self._add_issue("info", f"  Row {row}: {amount}")

        # Check for reasonable fee percentages
        high_fee_trades = []
        for tx in transactions:
            if tx.type == "Handel" and tx.gebyr and tx.ut:
                fee_percentage = (tx.gebyr / tx.ut) * 100
                if (
                    fee_percentage > HIGH_FEE_PERCENTAGE_THRESHOLD
                ):  # Fees over 5% might be suspicious
                    high_fee_trades.append((tx.row_num, fee_percentage))

        if high_fee_trades:
            self._add_issue(
                "warning",
                f"Found {len(high_fee_trades)} trades with high fees (>{HIGH_FEE_PERCENTAGE_THRESHOLD}%)",
            )
            for row, pct in high_fee_trades[:5]:
                self._add_issue("warning", f"  Row {row}: {pct:.1f}% fee")

    def _build_result(self, transactions: list[Transaction] = None) -> dict:
        """Build validation result dictionary"""
        # Convert structured issues back to legacy format for backward compatibility
        errors = [issue.message for issue in self.issues if issue.level == "error"]
        warnings = [issue.message for issue in self.issues if issue.level == "warning"]
        info = [issue.message for issue in self.issues if issue.level == "info"]

        return {
            "valid": len(errors) == 0,
            "transaction_count": len(transactions) if transactions else 0,
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "issues": self.issues.copy(),  # Include structured issues for advanced usage
        }

    def _export_problematic_transactions(
        self, csv_file: Path, transactions: list[Transaction], year: int
    ):
        """Export problematic transactions to files for debugging"""
        import csv
        from datetime import datetime
        import json

        # Extract problematic row numbers from issues
        problematic_rows = set()
        for issue in self.issues:
            if issue.level == "error" and issue.row_num:
                problematic_rows.add(issue.row_num)
            elif issue.level == "error" and "Row " in issue.message:
                try:
                    row_part = (
                        issue.message.split("Row ")[1].split(":")[0].split(" ")[0]
                    )
                    row_num = int(row_part)
                    problematic_rows.add(row_num)
                except (ValueError, IndexError):
                    continue

        if not problematic_rows:
            return

        # Create output directory
        output_dir = csv_file.parent

        # Export problematic CSV transactions
        problematic_csv_data = []
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_num, row in enumerate(reader, start=2):
                if row_num in problematic_rows:
                    row["csv_row"] = row_num
                    problematic_csv_data.append(row)

        if problematic_csv_data:
            csv_output_file = output_dir / f"problematic_transactions_{year}.csv"
            with open(csv_output_file, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=problematic_csv_data[0].keys())
                writer.writeheader()
                writer.writerows(problematic_csv_data)

            print(
                f"📄 Exported {len(problematic_csv_data)} problematic CSV transactions to: {csv_output_file}"
            )

        # Try to correlate with original JSON transactions
        original_json_file = output_dir / "cake_transactions_01_original.json"
        if original_json_file.exists():
            try:
                with open(original_json_file, encoding="utf-8") as f:
                    original_txs = json.load(f)

                problematic_original_txs = []

                # For each problematic CSV transaction, find matching original transactions
                for csv_tx in problematic_csv_data:
                    csv_timestamp = csv_tx["Tidspunkt"]
                    csv_inn_currency = csv_tx.get("Inn-Valuta", "")
                    csv_ut_currency = csv_tx.get("Ut-Valuta", "")
                    csv_note = csv_tx.get("Notat", "")

                    # Parse CSV timestamp for matching
                    try:
                        csv_dt = datetime.strptime(
                            csv_timestamp[:19], "%Y-%m-%d %H:%M:%S"
                        )
                    except ValueError:
                        continue

                    # Find matching original transactions (within 1 minute window)
                    for orig_tx in original_txs:
                        try:
                            orig_dt = datetime.fromisoformat(
                                orig_tx["date"].replace("Z", "+00:00")
                            ).replace(tzinfo=None)
                        except (ValueError, KeyError):
                            continue

                        # Match by timestamp (within 1 minute) and currency
                        time_diff = abs((csv_dt - orig_dt).total_seconds())
                        if time_diff <= 60:  # Within 1 minute
                            currency_match = (
                                orig_tx["coin_asset"] == csv_inn_currency
                                or orig_tx["coin_asset"] == csv_ut_currency
                            )
                            if currency_match:
                                # Add correlation info
                                correlated_tx = orig_tx.copy()
                                correlated_tx["csv_row"] = csv_tx["csv_row"]
                                correlated_tx["csv_type"] = csv_tx["Type"]
                                correlated_tx["csv_note"] = csv_note
                                problematic_original_txs.append(correlated_tx)

                # Remove duplicates and export original transactions
                if problematic_original_txs:
                    # Remove duplicates based on unique transaction properties
                    seen = set()
                    unique_original_txs = []
                    for tx in problematic_original_txs:
                        key = (
                            tx.get("transaction_id"),
                            tx["date"],
                            tx["coin_asset"],
                            tx["amount"],
                            tx["operation"],
                        )
                        if key not in seen:
                            seen.add(key)
                            unique_original_txs.append(tx)

                    json_output_file = (
                        output_dir / f"problematic_transactions_{year}_original.json"
                    )
                    with open(json_output_file, "w", encoding="utf-8") as f:
                        json.dump(unique_original_txs, f, indent=2, default=str)

                    print(
                        f"📋 Exported {len(unique_original_txs)} problematic original transactions to: {json_output_file}"
                    )

            except Exception as e:
                print(f"⚠️  Could not correlate with original JSON: {e}")

        # Create summary
        summary_file = output_dir / f"validation_errors_{year}.txt"
        errors = [issue.message for issue in self.issues if issue.level == "error"]
        warnings = [issue.message for issue in self.issues if issue.level == "warning"]

        with open(summary_file, "w", encoding="utf-8") as f:
            f.write(f"VALIDATION ERRORS SUMMARY - {year}\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Total errors: {len(errors)}\n")
            f.write(f"Total warnings: {len(warnings)}\n")
            f.write(f"Problematic CSV rows: {sorted(problematic_rows)}\n\n")
            f.write("ERRORS:\n")
            for error in errors:
                f.write(f"  • {error}\n")
            f.write("\nFILES CREATED:\n")
            if problematic_csv_data:
                f.write(
                    f"  • problematic_transactions_{year}.csv - Problematic CSV rows\n"
                )
            try:
                if original_json_file.exists():
                    f.write(
                        f"  • problematic_transactions_{year}_original.json - Correlated original transactions\n"
                    )
            except Exception:
                pass

        print(f"📝 Validation error summary saved to: {summary_file}")
