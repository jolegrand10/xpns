"""Module expense.py - home of class Expense"""

import datetime
import logging
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from xpns.expensetype import ExpenseType

logger = logging.getLogger(__name__)

DATE_FORMAT = "%d/%m/%Y"


@dataclass(frozen=True)
class Expense:
    """Represents an expense item to be entered in the expense form.

    Fields accept convenient raw input and are normalized on creation:
    - type: an ExpenseType, its screen label or its member name
    - date: a datetime.date or a "DD/MM/YYYY" string
    - amount: a Decimal, int, float or string ("43.50" or "43,50")
    - file: a Path or a string
    Invalid input raises ValueError.
    """

    type: ExpenseType
    date: datetime.date
    amount: Decimal
    subject: str
    supplier: str
    file: Path

    def __post_init__(self):
        # frozen dataclass: fields must be set through object.__setattr__
        object.__setattr__(self, "type", self._to_type(self.type))
        object.__setattr__(self, "date", self._to_date(self.date))
        object.__setattr__(self, "amount", self._to_amount(self.amount))
        object.__setattr__(self, "file", Path(self.file))
        logger.debug("Created %r", self)

    @staticmethod
    def _to_type(value):
        if isinstance(value, ExpenseType):
            return value
        try:
            return ExpenseType(value)
        except ValueError:
            pass
        try:
            return ExpenseType[value]
        except KeyError:
            raise ValueError(f"Unknown expense type: {value!r}") from None

    @staticmethod
    def _to_date(value):
        if isinstance(value, datetime.date):
            return value
        try:
            return datetime.datetime.strptime(value, DATE_FORMAT).date()
        except (TypeError, ValueError):
            raise ValueError(f"Invalid date, expected DD/MM/YYYY: {value!r}") from None

    @staticmethod
    def _to_amount(value):
        if isinstance(value, float):
            # go through str to avoid binary float artifacts
            value = str(value)
        if isinstance(value, str):
            value = value.strip().replace(",", ".")
        try:
            amount = Decimal(value)
        except (InvalidOperation, TypeError):
            raise ValueError(f"Invalid amount: {value!r}") from None
        if not amount.is_finite() or amount <= 0:
            raise ValueError(f"Amount must be a positive number: {value!r}")
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError(f"Amount has more than 2 decimals: {value!r}")
        return amount.quantize(Decimal("0.01"))

    @property
    def form_date(self):
        """Date as typed in the form: DD/MM/YYYY."""
        return self.date.strftime(DATE_FORMAT)

    @property
    def form_amount(self):
        """Amount as typed in the form: French decimal comma, 2 decimals."""
        return f"{self.amount:.2f}".replace(".", ",")


def main():
    """Smoke test: build expenses from raw and typed input, show form values."""
    from xpns.logsetup import setup_logger

    setup_logger()

    expense = Expense(
        type=ExpenseType.DEPLACEMENT,
        date="01/11/2026",
        amount=45.40,
        subject="Pass Navigo",
        supplier="Agence Navigo",
        file=r"2026-11\2026-01 Pass Navigo 45E40.pdf",
    )
    logger.info("Expense: %r", expense)
    logger.info("Form type:   %s", expense.type)
    logger.info("Form date:   %s", expense.form_date)
    logger.info("Form amount: %s", expense.form_amount)
    logger.info("File name:   %s", expense.file.name)

    same = Expense(
        type="DEPLACEMENT",
        date=datetime.date(2026, 11, 1),
        amount="45,40",
        subject="Pass Navigo",
        supplier="Agence Navigo",
        file=Path("2026-11") / "2026-01 Pass Navigo 45E40.pdf",
    )
    logger.info("Same expense from other input forms: %s", expense == same)

    for field, bad in [
        ("type", "VOYAGE"),
        ("date", "31/02/2026"),
        ("amount", "-5"),
        ("amount", "12.345"),
    ]:
        try:
            replace(expense, **{field: bad})
        except ValueError as exc:
            logger.info("Rejected %s: %s", field, exc)

    try:
        expense.amount = Decimal("1")
    except AttributeError as exc:
        logger.info("Frozen: %s", exc)


if __name__ == "__main__":
    main()
