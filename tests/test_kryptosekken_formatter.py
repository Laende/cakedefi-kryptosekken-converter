from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from src.constants import CSV_HEADERS
from src.kryptosekken_formatter import KryptosekkenFormatter
from src.models import KryptosekkenTransaction


class TestKryptosekkenFormatter:
    @pytest.fixture
    def sample_transactions(self):
        """Sample kryptosekken transactions for testing"""
        return [
            KryptosekkenTransaction(
                tidspunkt=datetime(2022, 2, 2, 19, 36, 32),
                type="Inntekt",
                inn=Decimal("0.5197701"),
                inn_valuta="ETH",
                ut=Decimal("12500.50"),
                ut_valuta="NOK",
                gebyr=None,
                gebyr_valuta=None,
                marked="CakeDeFi",
                notat="Staking reward",
            ),
            KryptosekkenTransaction(
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
            ),
        ]

    def test_csv_headers_correct(self):
        """Test that CSV headers match kryptosekken specification"""
        expected_headers = [
            "Tidspunkt",
            "Type",
            "Inn",
            "Inn-Valuta",
            "Ut",
            "Ut-Valuta",
            "Gebyr",
            "Gebyr-Valuta",
            "Marked",
            "Notat",
        ]

        assert CSV_HEADERS == expected_headers

    def test_to_csv_string_with_header(self, sample_transactions):
        """Test CSV string generation with header"""
        csv_string = KryptosekkenFormatter.to_csv_string(
            sample_transactions, include_header=True
        )

        lines = csv_string.strip().split("\n")

        # Should have header + 2 transaction lines
        assert len(lines) == 3

        # First line should be header
        header_line = lines[0].rstrip("\r\n")  # Strip any line endings
        assert (
            "Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat"
            == header_line
        )

        # Check first transaction line
        first_tx_line = lines[1]
        assert (
            "2022-02-02 19:36:32,Inntekt,0.5197701,ETH,12500.50,NOK,,," in first_tx_line
        )
        assert "CakeDeFi,Staking reward" in first_tx_line

        # Check second transaction line
        second_tx_line = lines[2]
        assert (
            "2022-02-02 20:12:09,Handel,124.82730894,DFI,0.11765613315,ETH,0.00059123685,ETH"
            in second_tx_line
        )

    def test_to_csv_string_without_header(self, sample_transactions):
        """Test CSV string generation without header"""
        csv_string = KryptosekkenFormatter.to_csv_string(
            sample_transactions, include_header=False
        )

        lines = csv_string.strip().split("\n")

        # Should have only 2 transaction lines (no header)
        assert len(lines) == 2

        # First line should be transaction data, not header
        assert not lines[0].startswith("Tidspunkt")
        assert lines[0].startswith("2022-02-02 19:36:32")

    def test_to_csv_file(self, sample_transactions):
        """Test writing transactions to CSV file"""
        with NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)

        try:
            KryptosekkenFormatter.to_csv_file(sample_transactions, tmp_path)

            # Verify file was created and has content
            assert tmp_path.exists()

            content = tmp_path.read_text(encoding="utf-8")
            lines = content.strip().split("\n")

            # Should have header + 2 transactions
            assert len(lines) == 3
            assert lines[0].startswith("Tidspunkt,Type")
            assert lines[1].startswith("2022-02-02 19:36:32,Inntekt")
            assert lines[2].startswith("2022-02-02 20:12:09,Handel")

        finally:
            # Cleanup
            if tmp_path.exists():
                tmp_path.unlink()

    def test_validate_valid_transaction(self, sample_transactions):
        """Test validation of valid transaction"""
        errors = KryptosekkenFormatter.validate_transaction(sample_transactions[0])
        assert errors == []

    def test_validate_transaction_missing_required_fields(self):
        """Test validation catches missing required fields"""
        # Transaction missing tidspunkt and type
        invalid_tx = KryptosekkenTransaction(
            tidspunkt=None,
            type="",
            inn=None,
            inn_valuta=None,
            ut=None,
            ut_valuta=None,
            gebyr=None,
            gebyr_valuta=None,
            marked=None,
            notat=None,
        )

        errors = KryptosekkenFormatter.validate_transaction(invalid_tx)

        assert len(errors) >= 3  # Should catch multiple errors
        error_text = " ".join(errors)
        assert "'Tidspunkt' is a required field" in error_text
        assert "'Type' is a required field" in error_text
        assert "At least one of 'Inn' or 'Ut' must be specified" in error_text

    def test_validate_transaction_currency_valuta_mismatch(self):
        """Test validation catches amount without corresponding valuta"""
        invalid_tx = KryptosekkenTransaction(
            tidspunkt=datetime.now(),
            type="Inntekt",
            inn=Decimal("100"),
            inn_valuta=None,  # Missing valuta
            ut=None,
            ut_valuta=None,
            gebyr=Decimal("5"),
            gebyr_valuta=None,  # Missing valuta
            marked=None,
            notat=None,
        )

        errors = KryptosekkenFormatter.validate_transaction(invalid_tx)

        error_text = " ".join(errors)
        assert "'Inn-Valuta' is required when 'Inn' is specified" in error_text
        assert "'Gebyr-Valuta' is required when 'Gebyr' is specified" in error_text

    def test_validate_invalid_currency_codes(self):
        """Test validation of currency codes"""
        # Invalid currency codes
        invalid_codes = [
            "TOOLONGCURRENCYCODEHERE",  # Too long (>16 chars)
            "BTC@",  # Invalid character
            "BTC!",  # Invalid character
            "",  # Empty
        ]

        for invalid_code in invalid_codes:
            invalid_tx = KryptosekkenTransaction(
                tidspunkt=datetime.now(),
                type="Inntekt",
                inn=Decimal("100"),
                inn_valuta=invalid_code,
                ut=None,
                ut_valuta=None,
                gebyr=None,
                gebyr_valuta=None,
                marked=None,
                notat=None,
            )

            errors = KryptosekkenFormatter.validate_transaction(invalid_tx)
            if invalid_code == "":
                # Empty string should trigger "required" error
                assert "'Inn-Valuta' is required when 'Inn' is specified" in " ".join(
                    errors
                )
            else:
                # Non-empty invalid codes should trigger "is invalid" error
                assert "is invalid" in " ".join(errors)

    def test_validate_valid_currency_codes(self):
        """Test validation accepts valid currency codes"""
        valid_codes = [
            "BTC",
            "ETH",
            "NOK",
            "USD",
            "BTC-DFI",
            "TOKEN123",
            "A",
            "csETH",
            "dBTC",
            "eth",
        ]

        for valid_code in valid_codes:
            valid_tx = KryptosekkenTransaction(
                tidspunkt=datetime.now(),
                type="Inntekt",
                inn=Decimal("100"),
                inn_valuta=valid_code,
                ut=None,
                ut_valuta=None,
                gebyr=None,
                gebyr_valuta=None,
                marked=None,
                notat=None,
            )

            errors = KryptosekkenFormatter.validate_transaction(valid_tx)
            # Should not have currency code validation errors
            currency_errors = [e for e in errors if "is invalid" in e]
            assert len(currency_errors) == 0

    def test_validate_transactions_list(self, sample_transactions):
        """Test validation of transaction list"""
        result = KryptosekkenFormatter.validate_transactions(sample_transactions)

        assert result["valid"] is True
        assert len(result["errors"]) == 0
        assert len(result["transaction_errors"]) == 0

    def test_generate_summary_report(self, sample_transactions):
        """Test summary report generation"""
        report = KryptosekkenFormatter.generate_summary_report(sample_transactions)

        assert "KRYPTOSEKKEN IMPORT SUMMARY" in report
        assert "Total transactions: 2" in report
        assert "Inntekt: 1" in report
        assert "Handel: 1" in report
        assert "ETH:" in report
        assert "DFI:" in report
        assert "2022-02-02 to 2022-02-02" in report

    def test_generate_summary_report_empty(self):
        """Test summary report with no transactions"""
        report = KryptosekkenFormatter.generate_summary_report([])
        assert report == "No transactions to summarize."

    def test_to_csv_files_by_year(self, sample_transactions):
        """Test generating separate CSV files by tax year"""
        from datetime import datetime
        from decimal import Decimal
        from tempfile import TemporaryDirectory

        # Add transactions for multiple years
        multi_year_transactions = sample_transactions + [
            KryptosekkenTransaction(
                tidspunkt=datetime(2023, 6, 15, 10, 0, 0),
                type="Handel",
                inn=Decimal("50.0"),
                inn_valuta="DFI",
                ut=Decimal("0.05"),
                ut_valuta="BTC",
                gebyr=None,
                gebyr_valuta=None,
                marked="CakeDeFi",
                notat="2023 trade",
            ),
            KryptosekkenTransaction(
                tidspunkt=datetime(2024, 1, 10, 15, 30, 0),
                type="Inntekt",
                inn=Decimal("5.0"),
                inn_valuta="ETH",
                ut=Decimal("8000.0"),
                ut_valuta="NOK",
                gebyr=None,
                gebyr_valuta=None,
                marked="CakeDeFi",
                notat="2024 reward",
            ),
        ]

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            # Generate yearly files
            yearly_files = KryptosekkenFormatter.to_csv_files_by_year(
                multi_year_transactions, tmp_path, "test_kryptosekken"
            )

            # Should create files for 2022, 2023, and 2024
            assert len(yearly_files) == 3
            assert 2022 in yearly_files
            assert 2023 in yearly_files
            assert 2024 in yearly_files

            # Check files exist and have correct names
            for year, file_path in yearly_files.items():
                assert file_path.exists()
                assert file_path.name == f"test_kryptosekken_{year}.csv"

                # Verify file content
                content = file_path.read_text(encoding="utf-8")
                lines = content.strip().split("\n")

                # Should have header + at least 1 transaction
                assert len(lines) >= 2
                assert lines[0].startswith("Tidspunkt,Type")

                # All transactions in file should be from the correct year
                for line in lines[1:]:  # Skip header
                    if line.strip():  # Skip empty lines
                        date_part = line.split(",")[0]
                        assert date_part.startswith(str(year))

    def test_to_csv_files_by_year_empty(self):
        """Test generating yearly files with no transactions"""
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            yearly_files = KryptosekkenFormatter.to_csv_files_by_year(
                [], tmp_path, "empty_test"
            )

            # Should return empty dict
            assert yearly_files == {}

    def test_to_csv_files_by_year_sorting(self):
        """Test that transactions within each year are sorted chronologically"""
        from datetime import datetime
        from decimal import Decimal
        from tempfile import TemporaryDirectory

        # Create transactions in reverse chronological order for same year
        transactions = [
            KryptosekkenTransaction(
                tidspunkt=datetime(
                    2022, 12, 31, 23, 59, 59
                ),  # Last transaction of year
                type="Inntekt",
                inn=Decimal("3.0"),
                inn_valuta="DFI",
                ut=Decimal("7.5"),
                ut_valuta="NOK",
                gebyr=None,
                gebyr_valuta=None,
                marked="CakeDeFi",
                notat="Last 2022",
            ),
            KryptosekkenTransaction(
                tidspunkt=datetime(2022, 1, 1, 0, 0, 1),  # First transaction of year
                type="Inntekt",
                inn=Decimal("1.0"),
                inn_valuta="DFI",
                ut=Decimal("2.5"),
                ut_valuta="NOK",
                gebyr=None,
                gebyr_valuta=None,
                marked="CakeDeFi",
                notat="First 2022",
            ),
        ]

        with TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            yearly_files = KryptosekkenFormatter.to_csv_files_by_year(
                transactions, tmp_path, "sorting_test"
            )

            # Should create one file for 2022
            assert len(yearly_files) == 1
            assert 2022 in yearly_files

            # Check that transactions are sorted chronologically in file
            file_2022 = yearly_files[2022]
            content = file_2022.read_text(encoding="utf-8")
            lines = content.strip().split("\n")

            # Should have header + 2 transactions
            assert len(lines) == 3

            # First transaction should be the January one (chronologically first)
            first_tx_line = lines[1]
            assert "2022-01-01 00:00:01" in first_tx_line
            assert "First 2022" in first_tx_line

            # Second transaction should be the December one
            second_tx_line = lines[2]
            assert "2022-12-31 23:59:59" in second_tx_line
            assert "Last 2022" in second_tx_line
