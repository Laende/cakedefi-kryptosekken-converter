"""
Handles USD to NOK currency conversion using historical exchange rates from
Norges Bank's official EXR.csv data file.
"""

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
from pathlib import Path

from .constants import (
    COL_BASE_CUR,
    COL_OBS_VALUE,
    COL_QUOTE_CUR,
    COL_TIME_PERIOD,
    FALLBACK_USD_NOK_RATE,
    LOOKUP_RANGE_DAYS,
    NOK_PRECISION,
)


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# Default path for exchange rate data
DEFAULT_EXR_FILE = Path(__file__).parent / "data" / "EXR.csv"


class CurrencyConverter:
    """USD to NOK converter using Norges Bank historical rates."""

    def __init__(self, exr_file: Path | None = None):
        """Initialize converter and load exchange rates."""
        # Use provided file or default
        self.exr_file = exr_file or DEFAULT_EXR_FILE
        self._rate_cache: dict[date, Decimal] = {}
        self._sorted_dates: list[date] = []
        self._load_exr_data()

    def _load_exr_data(self):
        """Load and cache exchange rates from CSV."""
        if not self.exr_file.exists():
            raise FileNotFoundError(
                f"Required exchange rate file not found: {self.exr_file}"
            )
        try:
            with self.exr_file.open("r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f, delimiter=";")
                for row in reader:
                    # Process USD/NOK rates only
                    if (
                        row.get(COL_BASE_CUR) == "USD"
                        and row.get(COL_QUOTE_CUR) == "NOK"
                    ):
                        try:
                            trade_date = datetime.strptime(
                                row[COL_TIME_PERIOD], "%Y-%m-%d"
                            ).date()
                            # Handle Norwegian decimal separator
                            rate_str = row[COL_OBS_VALUE].replace(",", ".")
                            self._rate_cache[trade_date] = Decimal(rate_str)
                        except (ValueError, KeyError):
                            logging.warning(
                                "Skipping malformed row in EXR file: %s", row
                            )
                            continue
        except (OSError, csv.Error) as e:
            logging.error("Failed to read or parse the EXR file: %s", e)
            return

        if self._rate_cache:
            # Sort dates for efficient lookups
            self._sorted_dates = sorted(self._rate_cache.keys())
            logging.info(
                "📈 Loaded %d USD/NOK rates from %s to %s.",
                len(self._sorted_dates),
                self._sorted_dates[0],
                self._sorted_dates[-1],
            )

    def _find_rate_for_date(self, target_date: date) -> Decimal | None:
        """Find exchange rate for date, with fallback to nearby dates."""
        # Check exact match first
        if target_date in self._rate_cache:
            return self._rate_cache[target_date]

        # Look backward for weekends/holidays
        for days_back in range(1, LOOKUP_RANGE_DAYS + 1):
            check_date = target_date - timedelta(days=days_back)
            if check_date in self._rate_cache:
                return self._rate_cache[check_date]

        # Look forward as last resort
        for days_forward in range(1, LOOKUP_RANGE_DAYS + 1):
            check_date = target_date + timedelta(days=days_forward)
            if check_date in self._rate_cache:
                return self._rate_cache[check_date]

        return None

    def get_usd_to_nok_rate(self, transaction_date: datetime) -> Decimal:
        """Get USD/NOK rate for date, with fallback to nearby dates."""
        trade_date = transaction_date.date()
        rate = self._find_rate_for_date(trade_date)

        if rate is None:
            logging.warning(
                "No exchange rate found for %s or nearby dates. Using fallback rate of %s.",
                trade_date,
                FALLBACK_USD_NOK_RATE,
            )
            return FALLBACK_USD_NOK_RATE

        return rate

    def convert_usd_to_nok(
        self, usd_amount: Decimal, transaction_date: datetime
    ) -> Decimal:
        """Convert USD amount to NOK using historical rates."""
        if usd_amount.is_zero():
            return Decimal("0")

        exchange_rate = self.get_usd_to_nok_rate(transaction_date)
        nok_amount = usd_amount * exchange_rate
        return nok_amount.quantize(NOK_PRECISION)

    def get_available_date_range(self) -> tuple[date, date] | None:
        """Return available date range for exchange rates."""
        if not self._sorted_dates:
            return None
        return self._sorted_dates[0], self._sorted_dates[-1]

    def has_rate_for_date(self, check_date: date) -> bool:
        """Check if rate exists for date (including nearby dates)."""
        return self._find_rate_for_date(check_date) is not None

    def get_cached_dates_count(self) -> int:
        """Return count of cached exchange rates."""
        return len(self._rate_cache)
