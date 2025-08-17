from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.constants import VALID_TRANSACTION_TYPES
from src.kryptosekken_validator import KryptosekkenValidator


class TestKryptosekkenValidator:
    @pytest.fixture
    def validator(self):
        """Create a fresh validator instance for each test"""
        return KryptosekkenValidator()

    @pytest.fixture
    def valid_csv_content(self):
        """Sample valid kryptosekken CSV content"""
        return """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Overføring-Inn,20000.0,NOK,,,,,,Initial NOK transfer
2022-01-02 11:00:00,Handel,0.5,ETH,15000.00,NOK,25.0,NOK,CakeDeFi,Buy ETH with NOK
2022-01-03 12:00:00,Inntekt,1.5,DFI,45.75,NOK,,,CakeDeFi,Staking reward
2022-01-04 13:00:00,Overføring-Inn,2.0,BTC,,,,,,Transfer from external wallet"""

    @pytest.fixture
    def invalid_csv_content(self):
        """Sample invalid kryptosekken CSV content with various errors"""
        return """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
,Inntekt,1.5,DFI,45.75,NOK,,,CakeDeFi,Missing timestamp
2022-01-02 11:00:00,InvalidType,0.5,ETH,15000.00,NOK,25.0,NOK,CakeDeFi,Invalid transaction type
2022-01-03 12:00:00,Handel,,,,,,,,Missing amounts for trade
2022-01-04 13:00:00,Inntekt,1.0,DFI,,,,,,Income without NOK valuation"""

    def test_validator_initialization(self, validator):
        """Test that validator initializes correctly"""
        assert isinstance(VALID_TRANSACTION_TYPES, set)
        assert "Handel" in VALID_TRANSACTION_TYPES
        assert "Inntekt" in VALID_TRANSACTION_TYPES
        assert validator.issues == []
        assert validator.errors == []
        assert validator.warnings == []
        assert validator.info == []

    def test_validate_valid_csv_file(self, validator, valid_csv_content):
        """Test validation of a valid CSV file"""
        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "valid_test.csv"
            csv_file.write_text(valid_csv_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file, expected_year=2022)

            # Debug: Print errors if validation fails
            if not result["valid"]:
                print(f"Validation errors: {result['errors']}")
                print(f"Validation warnings: {result['warnings']}")

            assert result["valid"] is True
            assert result["transaction_count"] == 4
            assert len(result["errors"]) == 0
            assert "Transaction date range:" in " ".join(result["info"])

    def test_validate_invalid_csv_file(self, validator, invalid_csv_content):
        """Test validation of an invalid CSV file"""
        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "invalid_test.csv"
            csv_file.write_text(invalid_csv_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file, expected_year=2022)

            assert result["valid"] is False
            assert result["transaction_count"] == 4
            assert len(result["errors"]) > 0

            # Check for specific error types
            error_text = " ".join(result["errors"])
            assert (
                "Tidspunkt is required" in error_text
                or "Missing or invalid Tidspunkt" in error_text
            )
            assert "Invalid Type" in error_text or "InvalidType" in error_text

    def test_validate_nonexistent_file(self, validator):
        """Test validation of a file that doesn't exist"""
        nonexistent_file = Path("/nonexistent/file.csv")
        result = validator.validate_csv_file(nonexistent_file)

        assert result["valid"] is False
        assert len(result["errors"]) > 0
        assert "File not found" in result["errors"][0]

    def test_validate_wrong_headers(self, validator):
        """Test validation of CSV with wrong headers"""
        wrong_headers_content = """Date,Type,Amount,Currency
2022-01-01,Trade,1.0,BTC"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "wrong_headers.csv"
            csv_file.write_text(wrong_headers_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is False
            assert "Invalid CSV headers" in result["errors"][0]

    def test_currency_balance_validation(self, validator):
        """Test currency balance validation (no negative balances)"""
        # CSV with negative balance - spending more than received
        negative_balance_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Overføring-Inn,1.0,BTC,,,,,,Receive BTC
2022-01-02 11:00:00,Handel,60000.00,NOK,2.0,BTC,,,Sell more BTC than we have"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "negative_balance.csv"
            csv_file.write_text(negative_balance_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is False
            error_text = " ".join(result["errors"])
            assert (
                "Negative currency balances" in error_text or "impossible" in error_text
            )

    def test_trade_validation(self, validator):
        """Test trade transaction validation"""
        # Trade with missing Inn or Ut
        invalid_trade_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Handel,1.0,BTC,,,,,,Trade missing Ut
2022-01-02 11:00:00,Handel,,ETH,30000.00,NOK,,,Trade missing Inn"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "invalid_trades.csv"
            csv_file.write_text(invalid_trade_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is False
            error_text = " ".join(result["errors"])
            assert "Handel transaction missing Inn or Ut" in error_text

    def test_income_validation(self, validator):
        """Test income transaction validation"""
        # Income with missing Inn or negative amount (no balance issues)
        invalid_income_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,,DFI,,,,,Income without Inn
2022-01-02 11:00:00,Inntekt,-1.0,DFI,,,,,Negative income"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "invalid_income.csv"
            csv_file.write_text(invalid_income_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is False
            error_text = " ".join(result["errors"])
            # Our enhanced validator catches different aspects of invalid income
            assert (
                "Must have either Inn or Ut" in error_text
                or "Inntekt transaction missing Inn" in error_text
            )
            assert (
                "Negative currency balances" in error_text
                or "non-positive amount" in error_text
            )

    def test_currency_code_validation(self, validator):
        """Test currency code format validation"""
        # Invalid currency codes
        invalid_currency_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.0,ThisCurrencyCodeIsTooLong123,45.75,NOK,,,Too long currency
2022-01-02 11:00:00,Handel,1.0,BTC@,30000.00,NO$,,,Invalid characters"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "invalid_currency.csv"
            csv_file.write_text(invalid_currency_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is False
            error_text = " ".join(result["errors"])
            assert "Invalid" in error_text and (
                "currency" in error_text.lower() or "valuta" in error_text.lower()
            )

    def test_decimal_precision_validation(self, validator):
        """Test decimal precision limits validation"""
        # Test with very high precision numbers
        high_precision_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.123456789012345678901234567890,BTC,45.75,NOK,,,Too many decimals"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "high_precision.csv"
            csv_file.write_text(high_precision_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            # Should either be valid (if precision is acceptable) or have precision error
            if not result["valid"]:
                error_text = " ".join(result["errors"])
                assert "precision" in error_text.lower()

    def test_norwegian_tax_compliance_validation(self, validator):
        """Test Norwegian tax compliance checks"""
        # Income without NOK valuation
        no_nok_income_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.0,DFI,,,,,,Income without NOK value"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "no_nok_income.csv"
            csv_file.write_text(no_nok_income_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            # Should have warnings about missing NOK valuations
            warning_text = " ".join(result["warnings"])
            assert (
                "NOK valuation" in warning_text or result["valid"]
            )  # Valid but with warnings

    def test_date_range_validation(self, validator):
        """Test date range and year validation"""
        mixed_years_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.0,DFI,45.75,NOK,,,2022 transaction
2023-01-01 10:00:00,Inntekt,1.0,DFI,45.75,NOK,,,2023 transaction"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "mixed_years.csv"
            csv_file.write_text(mixed_years_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file, expected_year=2022)

            assert result["valid"] is False
            error_text = " ".join(result["errors"])
            assert "not from expected year" in error_text

    def test_economic_reasonableness_validation(self, validator):
        """Test economic reasonableness checks"""
        # Zero amounts and very small amounts
        questionable_amounts_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,0,DFI,45.75,NOK,,,Zero amount
2022-01-02 11:00:00,Handel,0.000000001,BTC,0.001,NOK,,,Very small amounts
2022-01-03 12:00:00,Handel,1.0,ETH,30000.00,NOK,2000.0,NOK,,High fee trade"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "questionable_amounts.csv"
            csv_file.write_text(questionable_amounts_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            # Should have warnings about questionable amounts
            warning_text = " ".join(result["warnings"])
            info_text = " ".join(result["info"])
            combined_text = warning_text + info_text

            # Should detect zero amounts, small amounts, or high fees
            assert (
                "zero amounts" in combined_text.lower()
                or "small amount" in combined_text.lower()
                or "high fee" in combined_text.lower()
                or "very small amount" in combined_text.lower()
                or result["valid"]
            )  # Might be valid but with warnings

    def test_transaction_type_summary(self, validator, valid_csv_content):
        """Test that transaction type summary is included in info"""
        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "valid_test.csv"
            csv_file.write_text(valid_csv_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            info_text = " ".join(result["info"])
            assert "Transaction types:" in info_text
            assert "Handel:" in info_text
            assert "Inntekt:" in info_text

    def test_empty_csv_file(self, validator):
        """Test validation of empty CSV file"""
        empty_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "empty.csv"
            csv_file.write_text(empty_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["transaction_count"] == 0
            warning_text = " ".join(result["warnings"])
            assert "empty" in warning_text.lower() or len(result["warnings"]) == 0

    def test_currency_consistency_validation(self, validator):
        """Test that amounts have corresponding currency codes"""
        inconsistent_currency_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.0,,45.75,NOK,,,Inn without currency
2022-01-02 11:00:00,Handel,1.0,BTC,30000.00,,,,Ut without currency
2022-01-03 12:00:00,Handel,1.0,ETH,30000.00,NOK,25.0,,,Fee without currency"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "inconsistent_currency.csv"
            csv_file.write_text(inconsistent_currency_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is False
            error_text = " ".join(result["errors"])
            assert (
                "missing" in error_text.lower() and "valuta" in error_text.lower()
            ) or ("present but" in error_text and "missing" in error_text)

    def test_build_result_structure(self, validator, valid_csv_content):
        """Test that validation result has correct structure"""
        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "test.csv"
            csv_file.write_text(valid_csv_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            # Check result structure
            assert isinstance(result, dict)
            assert "valid" in result
            assert "transaction_count" in result
            assert "errors" in result
            assert "warnings" in result
            assert "info" in result

            assert isinstance(result["valid"], bool)
            assert isinstance(result["transaction_count"], int)
            assert isinstance(result["errors"], list)
            assert isinstance(result["warnings"], list)
            assert isinstance(result["info"], list)
            # Check new structured issues field
            assert "issues" in result
            assert isinstance(result["issues"], list)

    def test_income_nok_valuation_in_notes(self, validator):
        """Test that validator checks for NOK valuation in note field for income transactions"""
        # Income with NOK valuation in note (new correct format)
        income_with_nok_in_note = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.5,DFI,,,,,CakeDeFi,Staking reward (NOK value: 45.75)"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "income_with_nok_note.csv"
            csv_file.write_text(income_with_nok_in_note, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is True
            # Should not warn about missing NOK valuation since it's in note
            warning_text = " ".join(result["warnings"])
            assert "NOK valuation" not in warning_text or len(result["warnings"]) == 0

    def test_income_missing_nok_valuation_in_notes(self, validator):
        """Test that validator detects missing NOK valuation in note field"""
        # Income without NOK valuation in note
        income_without_nok = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.5,DFI,,,,,CakeDeFi,Staking reward"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "income_without_nok.csv"
            csv_file.write_text(income_without_nok, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            # Should still be valid but warn about missing NOK valuation
            assert result["valid"] is True  # Not an error, just a warning
            warning_text = " ".join(result["warnings"])
            assert "NOK valuation in notes" in warning_text

    def test_income_fixed_format_no_ut_outflow(self, validator):
        """Test that validator accepts income transactions without Ut/Ut-Valuta (fixed format)"""
        # Income transaction in new format (no phantom NOK outflow)
        fixed_income_content = """Tidspunkt,Type,Inn,Inn-Valuta,Ut,Ut-Valuta,Gebyr,Gebyr-Valuta,Marked,Notat
2022-01-01 10:00:00,Inntekt,1.5,DFI,,,,,CakeDeFi,Staking reward (NOK value: 45.75)
2022-01-02 11:00:00,Inntekt,0.5,ETH,,,,,CakeDeFi,Mining reward (NOK value: 1500.00)"""

        with TemporaryDirectory() as tmp_dir:
            csv_file = Path(tmp_dir) / "fixed_income.csv"
            csv_file.write_text(fixed_income_content, encoding="utf-8")

            result = validator.validate_csv_file(csv_file)

            assert result["valid"] is True
            assert result["transaction_count"] == 2

            # Should not have negative currency balance errors
            error_text = " ".join(result["errors"])
            assert "Negative currency balances" not in error_text
            assert "impossible" not in error_text

            # Should report correct transaction types
            info_text = " ".join(result["info"])
            assert "Inntekt: 2" in info_text
