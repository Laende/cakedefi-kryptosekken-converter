"""
This module provides a formatter to convert KryptosekkenTransaction objects
into the specific CSV format required for import into the Kryptosekken service.
"""

from collections import defaultdict
import csv
from decimal import Decimal
import io
from pathlib import Path
from typing import TypeAlias

from src.constants import (
    CSV_HEADERS,
    is_valid_currency_code,
    is_valid_decimal_precision,
)
from src.models import KryptosekkenTransaction


# Define a clear type alias for lists of transactions for cleaner method signatures
TransactionList: TypeAlias = list[KryptosekkenTransaction]


class KryptosekkenFormatter:
    """
    Formats KryptosekkenTransaction objects into a compliant CSV format.

    The class adheres to the specification from kryptosekken.no, ensuring
    correct headers and data formatting. All methods are class methods,

    making this a stateless utility.
    Reference: https://www.kryptosekken.no/regnskap/importer-csv-generisk
    """

    # Using shared constants from models.py to avoid duplication

    @classmethod
    def to_csv_file(
        cls, transactions: TransactionList, output_file: Path, encoding: str = "utf-8"
    ) -> None:
        """
        Writes a list of KryptosekkenTransaction objects to a CSV file.

        Args:
            transactions: The list of transactions to write.
            output_file: The path for the output CSV file.
            encoding: The file encoding to use.
        """
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with output_file.open("w", encoding=encoding, newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(tx.to_csv_row() for tx in transactions)

    @classmethod
    def to_csv_files_by_year(
        cls,
        transactions: TransactionList,
        output_dir: Path,
        file_prefix: str = "kryptosekken_import",
        encoding: str = "utf-8",
    ) -> dict:
        """
        Splits transactions by year and writes them to separate, sorted CSV files.

        This approach is standard for Norwegian tax reporting, which is filed annually.
        Transactions without a timestamp are ignored.

        Args:
            transactions: A list of all transactions to be processed.
            output_dir: The directory where the yearly CSV files will be saved.
            file_prefix: A prefix for the output filenames.
            encoding: The file encoding to use.

        Returns:
            A dictionary mapping each tax year (int) to its corresponding file path.
        """

        if not transactions:
            return {}

        output_dir.mkdir(parents=True, exist_ok=True)

        transactions_by_year = defaultdict(list)
        for tx in transactions:
            if tx.tidspunkt:
                transactions_by_year[tx.tidspunkt.year].append(tx)

        created_files = {}
        # Process years chronologically for deterministic output file generation.
        for year in sorted(transactions_by_year.keys()):
            year_transactions = transactions_by_year[year]
            # Sort transactions within each year's file to ensure chronological order.
            year_transactions.sort(key=lambda tx: tx.tidspunkt)

            output_file = output_dir / f"{file_prefix}_{year}.csv"
            cls.to_csv_file(year_transactions, output_file, encoding)
            created_files[year] = output_file

        return created_files

    @classmethod
    def to_csv_string(
        cls, transactions: list[KryptosekkenTransaction], include_header: bool = True
    ) -> str:
        """
        Converts a list of KryptosekkenTransaction objects to a CSV formatted string.
        """
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=CSV_HEADERS)

        if include_header:
            writer.writeheader()

        writer.writerows(tx.to_csv_row() for tx in transactions)
        return output.getvalue()

    @classmethod
    def validate_transaction(cls, tx: KryptosekkenTransaction) -> list[str]:
        """
        Validates a single transaction against Kryptosekken's import rules.

        Returns:
            A list of validation error messages. The list is empty if valid.
        """
        errors = []
        if not tx.tidspunkt:
            errors.append("'Tidspunkt' is a required field.")
        if not tx.type:
            errors.append("'Type' is a required field.")
        if tx.inn is None and tx.ut is None:
            errors.append("At least one of 'Inn' or 'Ut' must be specified.")

        # Consolidate validation of amount/currency pairs to avoid repetition.
        field_data = [
            ("Inn", tx.inn, tx.inn_valuta),
            ("Ut", tx.ut, tx.ut_valuta),
            ("Gebyr", tx.gebyr, tx.gebyr_valuta),
        ]

        for name_prefix, amount, currency in field_data:
            amount_name = name_prefix
            currency_name = (
                f"{name_prefix}-Valuta" if name_prefix != "Gebyr" else "Gebyr-Valuta"
            )

            if amount is not None:
                if not currency:
                    errors.append(
                        f"'{currency_name}' is required when '{amount_name}' is specified."
                    )
                if not is_valid_decimal_precision(amount):
                    errors.append(
                        f"'{amount_name}' ('{amount}') exceeds precision limits. "
                        "Max is 18 integer digits and 18 decimal places."
                    )

            if currency and not is_valid_currency_code(currency):
                errors.append(
                    f"'{currency_name}' ('{currency}') is invalid. "
                    "Must be 1-16 chars from A-Z, a-z, 0-9, -."
                )
        return errors

    @classmethod
    def validate_transactions(cls, transactions: TransactionList) -> dict:
        """
        Validates a list of transactions, aggregating all errors.

        Returns:
            A dictionary containing a validity flag and detailed error reports.
        """
        all_errors = []
        transaction_errors = {}

        for i, tx in enumerate(transactions, start=1):
            if tx_errors := cls.validate_transaction(tx):
                transaction_errors[i] = tx_errors
                all_errors.extend(f"Transaction {i}: {err}" for err in tx_errors)

        return {
            "valid": not all_errors,
            "errors": all_errors,
            "transaction_errors": transaction_errors,
        }

    # Validation methods moved to shared models.py

    @classmethod
    def generate_summary_report(cls, transactions: TransactionList) -> str:
        """
        Generates a human-readable summary report from a list of transactions.
        """
        if not transactions:
            return "No transactions to summarize."

        type_counts = defaultdict(int)
        currency_ins = defaultdict(Decimal)
        currency_outs = defaultdict(Decimal)

        for tx in transactions:
            type_counts[tx.type] += 1
            if tx.inn is not None and tx.inn_valuta:
                currency_ins[tx.inn_valuta] += tx.inn
            if tx.ut is not None and tx.ut_valuta:
                currency_outs[tx.ut_valuta] += tx.ut

        dates = [tx.tidspunkt for tx in transactions if tx.tidspunkt]
        date_range_str = ""
        if dates:
            min_date, max_date = min(dates), max(dates)
            date_range_str = f"\nDate range: {min_date.strftime('%Y-%m-%d')} to {max_date.strftime('%Y-%m-%d')}"

        report_lines = [
            "=" * 50,
            "KRYPTOSEKKEN IMPORT SUMMARY",
            "=" * 50,
            f"Total transactions: {len(transactions)}",
            "",
            "Transaction Types:",
            *[
                f"  - {tx_type}: {count}"
                for tx_type, count in sorted(type_counts.items())
            ],
            "",
            "Currency Totals (Incoming):",
            *[f"  - {cur}: {amt}" for cur, amt in sorted(currency_ins.items())],
        ]

        if currency_outs:
            report_lines.extend(
                [
                    "",
                    "Currency Totals (Outgoing):",
                    *[
                        f"  - {cur}: {amt}"
                        for cur, amt in sorted(currency_outs.items())
                    ],
                ]
            )

        report_lines.append(date_range_str)
        report_lines.append("=" * 50)

        return "\n".join(report_lines)
