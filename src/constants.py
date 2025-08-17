"""
Shared constants and validation functions for Kryptosekken CSV processing.

This module centralizes all constants, patterns, and validation logic
used across the validator, formatter, and other components.
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path
import re


# --- Kryptosekken CSV Format Constants ---

CSV_HEADERS = [
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

VALID_TRANSACTION_TYPES: set[str] = {
    "Handel",
    "Erverv",
    "Mining",
    "Inntekt",
    "Tap",
    "Forbruk",
    "Renteinntekt",
    "Overføring-Inn",
    "Overføring-Ut",
    "Gave-Inn",
    "Gave-Ut",
    "Tap-uten-fradrag",
    "Forvaltningskostnad",
}

SUPPORTED_TIMESTAMP_FORMATS = [
    "%Y-%m-%d %H:%M:%S",  # Preferred format
    "%Y-%m-%d %H:%M",  # Common variation without seconds
    "%Y-%m-%d %H:%M:%S.%f",  # With microseconds
    "%Y-%m-%d",  # Date only
    "%Y-%m-%dT%H:%M:%S",  # ISO format (T separator)
    "%Y-%m-%dT%H:%M:%S%z",  # ISO format with timezone
]

# --- Validation Constants ---

# Pre-compiled regex for performance
CURRENCY_CODE_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,16}$")

# Precision limits
MAX_DECIMAL_INTEGER_DIGITS = 18
MAX_DECIMAL_PLACES = 18

# Tolerance thresholds
BALANCE_TOLERANCE = Decimal("0.000001")
DUST_THRESHOLD = Decimal("0.000001")
HIGH_FEE_PERCENTAGE_THRESHOLD = Decimal("5")

# --- Balance Tracking Constants ---

# Default path for the balance state file
DEFAULT_BALANCE_FILE = Path("balance_state.json")

# Threshold to consider amounts negligible, avoiding floating point dust
NEGLIGIBLE_AMOUNT = Decimal("1e-8")

# --- Currency Conversion Constants ---

# Default path for the exchange rate data file
DEFAULT_EXR_FILE = Path("src/data/EXR.csv")

# CSV column names for Norges Bank EXR data
COL_BASE_CUR = "BASE_CUR"
COL_QUOTE_CUR = "QUOTE_CUR"
COL_TIME_PERIOD = "TIME_PERIOD"
COL_OBS_VALUE = "OBS_VALUE"

# Configuration for rate lookup logic
LOOKUP_RANGE_DAYS = 14
FALLBACK_USD_NOK_RATE = Decimal("10.0")

# Standard precision for NOK currency
NOK_PRECISION = Decimal("0.01")

# --- Validation Functions ---


def is_valid_currency_code(code: str) -> bool:
    """Validate currency code according to kryptosekken specs (1-16 chars: A-Z, a-z, 0-9, -)."""
    return bool(CURRENCY_CODE_PATTERN.match(code))


def is_valid_decimal_precision(amount: Decimal) -> bool:
    """Check if decimal meets kryptosekken precision requirements (max 18+18)."""
    try:
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
    except (InvalidOperation, ValueError):
        return False

    sign, digits, exponent = amount.as_tuple()

    # Calculate integer and decimal parts
    num_digits = len(digits)
    decimal_places = -exponent if exponent < 0 else 0
    integer_digits = (
        max(0, num_digits + exponent) if exponent >= 0 else num_digits - abs(exponent)
    )

    return (
        integer_digits <= MAX_DECIMAL_INTEGER_DIGITS
        and decimal_places <= MAX_DECIMAL_PLACES
    )
