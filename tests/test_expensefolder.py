"""Tests for module expensefolder.py - functions for building an expense report
from a monthly folder"""

import datetime
import logging
from decimal import Decimal
from pathlib import Path

import pytest

from xpns.expensefolder import (
    MEMO,
    expense_file,
    expense_folder,
    folder_report,
    half,
    my_remove,
    parse_date,
    parse_folder_name,
    report_subject,
    split_amounts,
    tokenize,
)
from xpns.expensetype import ExpenseType

TODAY = datetime.date(2026, 11, 9)


def make_folder(parent, name, files=(), subfolders=()):
    """Create a folder with empty files and subfolders; return its path."""
    folder = parent / name
    folder.mkdir()
    for file in files:
        (folder / file).touch()
    for sub in subfolders:
        (folder / sub).mkdir()
    return folder


# --- folder name and subject ---


@pytest.mark.parametrize(
    "name, expected", [("2026-10", (2026, 10)), ("2025-01", (2025, 1))]
)
def test_parse_folder_name(name, expected):
    assert parse_folder_name(name) == expected


@pytest.mark.parametrize(
    "name", ["2026-13", "2026-00", "Octobre", "2026-10 bis", "26-10"]
)
def test_parse_folder_name_rejected(name):
    with pytest.raises(ValueError):
        parse_folder_name(name)


@pytest.mark.parametrize(
    "month, expected",
    [
        (1, "Frais de Janvier 2026"),
        (2, "Frais de Février 2026"),
        (3, "Frais de Mars 2026"),
        (4, "Frais d'Avril 2026"),
        (5, "Frais de Mai 2026"),
        (6, "Frais de Juin 2026"),
        (7, "Frais de Juillet 2026"),
        (8, "Frais d'Août 2026"),
        (9, "Frais de Septembre 2026"),
        (10, "Frais d'Octobre 2026"),
        (11, "Frais de Novembre 2026"),
        (12, "Frais de Décembre 2026"),
    ],
)
def test_report_subject(month, expected):
    assert report_subject(2026, month) == expected


# --- helpers ---


def test_my_remove_first_occurrence_only_and_copy():
    items = ["a", "OVH", "b", "OVH"]
    assert my_remove(items, "OVH") == ["a", "b", "OVH"]
    assert items == ["a", "OVH", "b", "OVH"]


@pytest.mark.parametrize(
    "amount, expected",
    [("33.31", "16.66"), ("33.29", "16.64"), ("61.01", "30.50"), ("20.00", "10.00")],
)
def test_half_bankers_rounding(amount, expected):
    assert half(Decimal(amount)) == Decimal(expected)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("2026-10-01 AWS 33E31", ["2026-10-01", "AWS", "33E31"]),
        ("Dej @ chez Paul", ["Dej", "@", "chez", "Paul"]),
        ("Câble USB@Amazon", ["Câble", "USB", "@", "Amazon"]),
        ("Dej @chez Paul", ["Dej", "@", "chez", "Paul"]),
        ("a  b", ["a", "b"]),
    ],
)
def test_tokenize(name, expected):
    assert tokenize(name) == expected


# --- date ---


@pytest.mark.parametrize(
    "token, expected",
    [
        ("2026-10-15", datetime.date(2026, 10, 15)),
        ("2026-01", datetime.date(2026, 1, 1)),
    ],
)
def test_parse_date(token, expected):
    assert parse_date(token) == expected


@pytest.mark.parametrize(
    "token", ["Navigo", "2026-02-30", "2026-13", "26-10-01", "2026-1-5"]
)
def test_parse_date_rejected(token):
    with pytest.raises(ValueError):
        parse_date(token)


# --- amounts ---


@pytest.mark.parametrize(
    "tokens, rest, amount",
    [
        (["AWS", "33E31"], ["AWS"], "33.31"),
        (["AWS", "33EUR31"], ["AWS"], "33.31"),
        (["Medium", "34E52", "40USD00"], ["Medium"], "34.52"),
        (["Medium", "40USD00", "34E52"], ["Medium"], "34.52"),
        (["Livre", "12E00", "8E00"], None, None),
    ],
)
def test_split_amounts(tokens, rest, amount):
    if rest is None:
        with pytest.raises(ValueError, match="More than one amount in euros"):
            split_amounts(tokens)
    else:
        assert split_amounts(tokens) == (rest, Decimal(amount))


@pytest.mark.parametrize(
    "tokens",
    [
        ["Navigo"],
        [],
        ["Navigo", "86E4"],
        ["Navigo", "86USD40"],
        ["Medium", "34E52", "40USD"],
        ["Navigo", "86E40", "Octobre"],
    ],
)
def test_split_amounts_no_euro(tokens):
    with pytest.raises(ValueError, match="No amount in euros"):
        split_amounts(tokens)


# --- file names ---


@pytest.mark.parametrize(
    "name, type_, date, amount, subject, supplier",
    [
        (
            "2026-10-01 AWS 33E31.pdf",
            ExpenseType.HEBERGEMENT_WEB,
            "01/10/2026",
            "33,31",
            "Hébergement applicatif",
            "AWS",
        ),
        (
            "2026-10-02 OVH Serveur dédié 12E00.pdf",
            ExpenseType.HEBERGEMENT_WEB,
            "02/10/2026",
            "12,00",
            "Serveur dédié",
            "OVH",
        ),
        (
            "2026-10-03 Domaine OVH Mail 2E40 3USD10.pdf",
            ExpenseType.HEBERGEMENT_WEB,
            "03/10/2026",
            "2,40",
            "Domaine Mail",
            "OVH",
        ),
        (
            "2026-10 Navigo 86E40.pdf",
            ExpenseType.DEPLACEMENT,
            "01/10/2026",
            "86,40",
            "Pass Navigo",
            "Agence Navigo",
        ),
        (
            "2026-10-04 Pass Navigo Octobre 86E40.pdf",
            ExpenseType.DEPLACEMENT,
            "04/10/2026",
            "86,40",
            "Pass Navigo",
            "Agence Navigo",
        ),
        (
            "2026-10-05 Orange Fixe 33E31.pdf",
            ExpenseType.INTERNET_ET_TELEPHONE,
            "05/10/2026",
            "16,66",
            "(1/2)*@",
            "Orange",
        ),
        (
            "2026-10-05 Orange Internet 30E00.pdf",
            ExpenseType.INTERNET_ET_TELEPHONE,
            "05/10/2026",
            "15,00",
            "(1/2)*@",
            "Orange",
        ),
        (
            "2026-10-06 Orange Mobile 20E00.PDF",
            ExpenseType.INTERNET_ET_TELEPHONE,
            "06/10/2026",
            "10,00",
            "(1/2)*tel",
            "Orange",
        ),
        (
            "2026-10-07 Orange 60E00.pdf",
            ExpenseType.INTERNET_ET_TELEPHONE,
            "07/10/2026",
            "30,00",
            "(1/2)*(@ + tel)",
            "Orange",
        ),
        (
            "2026-10-07 Fixe @ Orange 60E00.pdf",
            ExpenseType.INTERNET_ET_TELEPHONE,
            "07/10/2026",
            "30,00",
            "(1/2)*(@ + tel)",
            "Orange",
        ),
        (
            "2026-10-08 Dej 15E50.pdf",
            ExpenseType.REPAS_SEUL,
            "08/10/2026",
            "15,50",
            "Déjeuner",
            "",
        ),
        (
            "2026-10-09 Dej @ chez Paul 18EUR00.pdf",
            ExpenseType.REPAS_SEUL,
            "09/10/2026",
            "18,00",
            "Déjeuner",
            "chez Paul",
        ),
        (
            "2026-10-10 Câble USB@Amazon 9E99.pdf",
            ExpenseType.ACHATS_PETITS_EQUIPEMENTS,
            "10/10/2026",
            "9,99",
            "Câble USB",
            "Amazon",
        ),
        (
            "2026-10-11 Livre Python @ Amazon 39E90 45USD00.pdf",
            ExpenseType.DOCUMENTATION,
            "11/10/2026",
            "39,90",
            "Livre Python",
            "Amazon",
        ),
        (
            "2026-10-12 Cleverbridge 49E00.pdf",
            ExpenseType.LOGICIELS,
            "12/10/2026",
            "49,00",
            "",
            "Cleverbridge",
        ),
        (
            "2026-10-13 Corel Mindmanager 99E00.pdf",
            ExpenseType.LOGICIELS,
            "13/10/2026",
            "99,00",
            "Mindmanager",
            "Corel",
        ),
        (
            "2026-10-14 Medium 5E00.pdf",
            ExpenseType.DOCUMENTATION,
            "14/10/2026",
            "5,00",
            "",
            "Medium",
        ),
        (
            "2025-12-02 Abonnement GG @ Medium 34E52 40USD00.pdf",
            ExpenseType.DOCUMENTATION,
            "02/12/2025",
            "34,52",
            "Abonnement GG",
            "Medium",
        ),
    ],
)
def test_expense_file_accepted(name, type_, date, amount, subject, supplier):
    expense = expense_file(Path(name))
    assert expense.type is type_
    assert expense.form_date == date
    assert expense.form_amount == amount
    assert expense.subject == subject
    assert expense.supplier == supplier
    assert expense.file == Path(name)


@pytest.mark.parametrize("name", ["2026-10-15 Facture.docx", "Capture.png", "notes"])
def test_expense_file_not_pdf_discarded(name, caplog):
    with caplog.at_level(logging.INFO):
        assert expense_file(Path(name)) is None
    assert "not a PDF" in caplog.text


@pytest.mark.parametrize(
    "name, field",
    [
        ("2026-10-08 Dej 15E50.pdf", "supplier"),
        ("2026-10-14 Medium 5E00.pdf", "subject"),
    ],
)
def test_expense_file_missing_field_warning(name, field, caplog):
    with caplog.at_level(logging.WARNING):
        assert expense_file(Path(name)) is not None
    assert f"Missing {field}" in caplog.text


@pytest.mark.parametrize(
    "name, reason",
    [
        ("Navigo 86E40.pdf", "No date"),
        ("2026-02-30 Navigo 86E40.pdf", "Invalid date"),
        ("2026-10-17 Navigo.pdf", "No amount in euros"),
        ("2026-10-18 Navigo 86E4.pdf", "No amount in euros"),
        ("2026-10-19 Navigo 86USD40.pdf", "No amount in euros"),
        ("2026-10-20 Navigo 86E40 12EUR00.pdf", "More than one amount in euros"),
        ("2026-10-21 Dej chez Paul 18E00.pdf", "No expense type"),
        ("2026-10-22 Fnac 25E00.pdf", "No expense type"),
        ("2026-10-23 0E00.pdf", "No expense type"),
        (" .pdf", "Empty name"),
    ],
)
def test_expense_file_rejected(name, reason):
    with pytest.raises(ValueError, match=reason):
        expense_file(Path(name))


# --- folders ---


def test_folder_report_clean(tmp_path):
    folder = make_folder(
        tmp_path,
        "2026-10",
        files=["2026-10-01 AWS 33E31.pdf", "2026-01 Pass Navigo 45E40.pdf"],
    )
    report, errors = folder_report(folder, today=TODAY)
    assert errors == []
    assert report["date"] == TODAY
    assert report["subject"] == "Frais d'Octobre 2026"
    assert report["memo"] == MEMO
    # alphabetical order of file names
    assert [e.file.name for e in report["expenses"]] == [
        "2026-01 Pass Navigo 45E40.pdf",
        "2026-10-01 AWS 33E31.pdf",
    ]


def test_folder_report_keeps_accepted_expenses_and_errors(tmp_path):
    folder = make_folder(
        tmp_path,
        "2026-12",
        files=["2026-12-01 AWS 33E31.pdf", "2026-12-02 Fnac 25E00.pdf", "notes.txt"],
        subfolders=["old"],
    )
    report, errors = folder_report(folder, today=TODAY)
    assert [e.supplier for e in report["expenses"]] == ["AWS"]
    assert len(errors) == 1
    assert errors[0].startswith("2026-12-02 Fnac 25E00.pdf: No expense type")


def test_folder_report_default_date_is_today(tmp_path):
    folder = make_folder(tmp_path, "2026-10", files=["2026-10-01 AWS 33E31.pdf"])
    report, _ = folder_report(folder)
    assert report["date"] == datetime.date.today()


def test_expense_folder_clean(tmp_path):
    folder = make_folder(tmp_path, "2026-10", files=["2026-10-01 AWS 33E31.pdf"])
    report = expense_folder(folder, today=TODAY)
    assert report["subject"] == "Frais d'Octobre 2026"
    assert len(report["expenses"]) == 1


def test_expense_folder_lists_all_files_to_rename(tmp_path):
    folder = make_folder(
        tmp_path,
        "2026-12",
        files=[
            "2026-12-01 AWS 33E31.pdf",
            "2026-12-02 Fnac 25E00.pdf",
            "2026-12-03 Navigo.pdf",
        ],
    )
    with pytest.raises(ValueError, match="2 file") as exc_info:
        expense_folder(folder)
    message = str(exc_info.value)
    assert "Fnac" in message
    assert "2026-12-03 Navigo.pdf" in message


@pytest.mark.parametrize(
    "name, files, reason",
    [
        ("2026-13", ["2026-12-01 AWS 33E31.pdf"], "Invalid month"),
        ("Octobre", ["2026-12-01 AWS 33E31.pdf"], "YYYY-MM"),
        ("2026-11", [], "No file"),
        ("2026-09", ["scan.png", "facture.docx"], "No expense"),
    ],
)
def test_expense_folder_rejected(tmp_path, name, files, reason):
    folder = make_folder(tmp_path, name, files=files)
    with pytest.raises(ValueError, match=reason):
        expense_folder(folder)


def test_expense_folder_missing(tmp_path):
    with pytest.raises(ValueError, match="Not a folder"):
        expense_folder(tmp_path / "2026-10")


def test_expense_folder_subfolders_only(tmp_path):
    folder = make_folder(tmp_path, "2026-10", subfolders=["old"])
    with pytest.raises(ValueError, match="No file"):
        expense_folder(folder)
