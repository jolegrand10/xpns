"""Tests for module expense.py - class Expense"""

import datetime
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from pathlib import Path

import pytest

from xpns.expense import Expense
from xpns.expensetype import ExpenseType

RAW = dict(
    type=ExpenseType.DEPLACEMENT,
    date="01/11/2026",
    amount=45.40,
    subject="Pass Navigo",
    supplier="Agence Navigo",
    file=r"2026-11\2026-01 Pass Navigo 45E40.pdf",
)


@pytest.fixture
def expense():
    return Expense(**RAW)


# --- normalization of raw input ---


def test_fields_are_normalized(expense):
    assert expense.type is ExpenseType.DEPLACEMENT
    assert expense.date == datetime.date(2026, 11, 1)
    assert expense.amount == Decimal("45.40")
    assert isinstance(expense.amount, Decimal)
    assert expense.subject == "Pass Navigo"
    assert expense.supplier == "Agence Navigo"
    assert expense.file == Path("2026-11", "2026-01 Pass Navigo 45E40.pdf")


def test_same_expense_from_other_input_forms(expense):
    same = Expense(
        type="DEPLACEMENT",
        date=datetime.date(2026, 11, 1),
        amount="45,4",
        subject="Pass Navigo",
        supplier="Agence Navigo",
        file=Path("2026-11") / "2026-01 Pass Navigo 45E40.pdf",
    )
    assert same == expense


@pytest.mark.parametrize(
    "value",
    [ExpenseType.FRAIS_DE_MISSION, "FRAIS DE MISSION", "FRAIS_DE_MISSION"],
)
def test_type_accepts_member_label_or_name(value):
    assert replace(Expense(**RAW), type=value).type is ExpenseType.FRAIS_DE_MISSION


def test_type_accepts_label_with_typo():
    expense = Expense(**{**RAW, "type": "ACHATS (intracommunautaire))"})
    assert expense.type is ExpenseType.ACHATS_INTRACOMMUNAUTAIRE


@pytest.mark.parametrize(
    "value, expected",
    [
        (43.50, "43.50"),
        (43, "43.00"),
        ("43.5", "43.50"),
        ("43,50", "43.50"),
        (" 43,50 ", "43.50"),
        (Decimal("43.5"), "43.50"),
        (0.1, "0.10"),
    ],
)
def test_amount_conversion(value, expected):
    amount = Expense(**{**RAW, "amount": value}).amount
    assert amount == Decimal(expected)
    assert str(amount) == expected


# --- form values ---


def test_form_values(expense):
    assert str(expense.type) == "DEPLACEMENT"
    assert expense.form_date == "01/11/2026"
    assert expense.form_amount == "45,40"
    assert expense.file.name == "2026-01 Pass Navigo 45E40.pdf"


def test_form_date_pads_day_and_month():
    expense = Expense(**{**RAW, "date": datetime.date(2026, 3, 5)})
    assert expense.form_date == "05/03/2026"


# --- rejected input ---


@pytest.mark.parametrize(
    "field, bad",
    [
        ("type", "VOYAGE"),
        ("type", "deplacement"),
        ("type", None),
        ("date", "31/02/2026"),
        ("date", "2026-11-01"),
        ("date", ""),
        ("date", None),
        ("amount", "-5"),
        ("amount", 0),
        ("amount", "12.345"),
        ("amount", "abc"),
        ("amount", ""),
        ("amount", None),
        ("amount", "NaN"),
        ("amount", "Infinity"),
    ],
)
def test_invalid_input_rejected(expense, field, bad):
    with pytest.raises(ValueError):
        replace(expense, **{field: bad})


def test_error_message_shows_repr_of_value():
    with pytest.raises(ValueError, match=r"'31/02/2026'"):
        Expense(**{**RAW, "date": "31/02/2026"})


# --- frozen behavior ---


def test_frozen(expense):
    with pytest.raises(FrozenInstanceError):
        expense.amount = Decimal("1")


def test_replace_creates_new_validated_expense(expense):
    fixed = replace(expense, amount="45,40")
    assert fixed.amount == Decimal("45.40")
    assert expense.amount == Decimal("45.40")


def test_hashable(expense):
    assert len({expense, Expense(**RAW)}) == 1
