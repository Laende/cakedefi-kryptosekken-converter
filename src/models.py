from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class KryptosekkenTransaction:
    """Unified transaction model for both validation and output."""

    tidspunkt: datetime | None
    type: str
    inn: Decimal | None
    inn_valuta: str | None
    ut: Decimal | None
    ut_valuta: str | None
    gebyr: Decimal | None
    gebyr_valuta: str | None
    marked: str | None
    notat: str | None
    row_num: int | None = None  # Optional field for validation use

    def to_csv_row(self) -> dict:
        """Converts the transaction back to a dictionary for CSV writing."""
        return {
            "Tidspunkt": self.tidspunkt.strftime("%Y-%m-%d %H:%M:%S")
            if self.tidspunkt
            else "",
            "Type": self.type or "",
            "Inn": str(self.inn) if self.inn is not None else "",
            "Inn-Valuta": self.inn_valuta or "",
            "Ut": str(self.ut) if self.ut is not None else "",
            "Ut-Valuta": self.ut_valuta or "",
            "Gebyr": str(self.gebyr) if self.gebyr is not None else "",
            "Gebyr-Valuta": self.gebyr_valuta or "",
            "Marked": self.marked or "",
            "Notat": self.notat or "",
        }

    @classmethod
    def for_validation(cls, row_num: int, **kwargs) -> "KryptosekkenTransaction":
        """Create transaction for validation with row number."""
        return cls(row_num=row_num, **kwargs)

    @classmethod
    def for_output(cls, **kwargs) -> "KryptosekkenTransaction":
        """Create transaction for output (no row number)."""
        return cls(row_num=None, **kwargs)


@dataclass
class CakeTransaction:
    """Represents a transaction from CakeDeFi CSV export"""

    date: datetime
    operation: str
    amount: Decimal
    coin_asset: str
    fiat_value: Decimal
    fiat_currency: str
    transaction_id: str | None
    withdrawal_address: str | None
    reference: str | None
    related_reference_id: str | None
    original_index: int | None = None  # Preserve original CSV order for tie-breaking

    @classmethod
    def from_csv_row(
        cls, row: dict, original_index: int | None = None
    ) -> "CakeTransaction":
        """Create CakeTransaction from CSV row dict"""
        return cls(
            date=datetime.fromisoformat(row["Date"]),
            operation=row["Operation"],
            amount=Decimal(str(row["Amount"])),
            coin_asset=row["Coin/Asset"],
            fiat_value=Decimal(str(row["FIAT value"])),
            fiat_currency=row["FIAT currency"],
            transaction_id=row["Transaction ID"] if row["Transaction ID"] else None,
            withdrawal_address=row["Withdrawal address"]
            if row["Withdrawal address"]
            else None,
            reference=row["Reference"] if row["Reference"] else None,
            related_reference_id=row["Related reference ID"]
            if row["Related reference ID"]
            else None,
            original_index=original_index,
        )


# Create type alias for backward compatibility
Transaction = KryptosekkenTransaction
