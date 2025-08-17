from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from src.currency_converter import CurrencyConverter


class TestCurrencyConverter:
    @pytest.fixture
    def converter(self):
        """Create currency converter with real EXR data"""
        exr_file = Path(__file__).parent.parent / "src" / "data" / "EXR.csv"
        return CurrencyConverter(exr_file)

    def test_load_exr_data(self, converter):
        """Test that EXR data is loaded correctly"""
        # Should have loaded data
        assert converter.get_cached_dates_count() > 0

        # Should have data from 2022 to recent
        start_date, end_date = converter.get_available_date_range()
        assert start_date <= date(2022, 2, 1)  # Around when our transaction data starts
        assert end_date >= date(2024, 1, 1)  # Should have recent data

    def test_get_exact_rate(self, converter):
        """Test getting exchange rate for exact date"""
        # Test a date we know should exist (early 2022)
        test_date = datetime(2022, 1, 3)
        rate = converter.get_usd_to_nok_rate(test_date)

        assert isinstance(rate, Decimal)
        assert rate > 0
        # USD/NOK rate should be reasonable (between 8-12 for this period)
        assert 8 <= rate <= 12

    def test_get_weekend_rate(self, converter):
        """Test getting rate for weekend (should use previous business day)"""
        # January 8, 2022 was a Saturday
        weekend_date = datetime(2022, 1, 8)
        rate = converter.get_usd_to_nok_rate(weekend_date)

        assert isinstance(rate, Decimal)
        assert rate > 0
        # Should get a rate from Friday or earlier
        assert 8 <= rate <= 12

    def test_convert_usd_to_nok(self, converter):
        """Test USD to NOK conversion"""
        test_date = datetime(2022, 2, 2, 19, 36, 32)  # From our sample data
        usd_amount = Decimal("1396.08")

        nok_amount = converter.convert_usd_to_nok(usd_amount, test_date)

        assert isinstance(nok_amount, Decimal)
        assert nok_amount > 0
        # Should be roughly usd_amount * 9-10 (approximate rate for early 2022)
        assert Decimal("12000") <= nok_amount <= Decimal("15000")

    def test_convert_zero_amount(self, converter):
        """Test converting zero amount"""
        test_date = datetime(2022, 2, 2)
        result = converter.convert_usd_to_nok(Decimal("0"), test_date)

        assert result == Decimal("0")

    def test_convert_negative_amount(self, converter):
        """Test converting negative amount (fees/losses)"""
        test_date = datetime(2022, 2, 2)
        usd_amount = Decimal("-130.0")

        nok_amount = converter.convert_usd_to_nok(usd_amount, test_date)

        assert nok_amount < 0
        assert abs(nok_amount) > abs(usd_amount)  # Should be larger in NOK

    def test_rate_precision(self, converter):
        """Test that converted amounts have proper precision"""
        test_date = datetime(2022, 2, 2)
        usd_amount = Decimal("123.456789")

        nok_amount = converter.convert_usd_to_nok(usd_amount, test_date)

        # Should be rounded to 2 decimal places (NOK currency precision)
        assert nok_amount.as_tuple().exponent == -2

    def test_has_rate_for_date(self, converter):
        """Test checking if rate exists for date"""
        # Should have rate for business day in 2022
        business_day = date(2022, 1, 3)  # Monday
        assert converter.has_rate_for_date(business_day)

        # Should also find rate for nearby weekend
        weekend_day = date(2022, 1, 8)  # Saturday
        assert converter.has_rate_for_date(weekend_day)

    def test_transaction_date_with_timezone(self, converter):
        """Test that timezone info is handled correctly"""
        # Our CakeDeFi data has timezone info
        tz_date = datetime.fromisoformat("2022-02-02T19:36:32+01:00")
        rate = converter.get_usd_to_nok_rate(tz_date)

        assert isinstance(rate, Decimal)
        assert rate > 0
