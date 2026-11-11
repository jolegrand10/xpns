"""Tests for module expensetype.py - class ExpenseType"""

import pytest

from xpns.expensetype import ExpenseType

# Exact labels as displayed in the form's combo box, typos included.
SCREEN_LABELS = [
    "ACHAT MARCHANDISES (Revente)",
    "ACHATS (intracommunautaire))",
    "ACHATS (petits équipements)",
    "CADEAUX A LA CLIENTELE",
    "COMMUNICATION",
    "DEPLACEMENT",
    "DOCUMENTATION",
    "ENTRETIEN",
    "FORMATION",
    "FOURNISSEUR",
    "FOURNITURE NON STOCKABLE energ",
    "FOURNITURES DE BUREAU",
    "FRAIS DE MISSION",
    "FRAIS POSTAUX",
    "HEBERGEMENT WEB",
    "HONORAIRES",
    "HOTEL",
    "Internet et téléphone (50 %)",
    "LOCATION IMMOBILIERE",
    "LOCATION MOBILIERE",
    "LOGICIELS",
    "PEAGE",
    "PRESSE",
    "PUBLICATION",
    "RECEPTIONS",
    "REPAS INVITATION",
    "REPAS SEUL",
    "TRANSPORT",
]


def test_values_match_screen_labels_in_order():
    assert [e.value for e in ExpenseType] == SCREEN_LABELS


def test_count():
    assert len(ExpenseType) == 28


@pytest.mark.parametrize("label", SCREEN_LABELS)
def test_lookup_by_label(label):
    assert ExpenseType(label).value == label


def test_typos_preserved():
    assert ExpenseType.ACHATS_INTRACOMMUNAUTAIRE.value.endswith("))")
    assert ExpenseType.FOURNITURE_NON_STOCKABLE_ENERGIE.value.endswith("energ")


def test_accents_preserved():
    assert ExpenseType.ACHATS_PETITS_EQUIPEMENTS.value == "ACHATS (petits équipements)"
    assert ExpenseType.INTERNET_ET_TELEPHONE.value == "Internet et téléphone (50 %)"


def test_str_gives_label():
    assert str(ExpenseType.HOTEL) == "HOTEL"
    assert f"{ExpenseType.REPAS_SEUL}" == "REPAS SEUL"


def test_equal_to_plain_string():
    assert ExpenseType.PEAGE == "PEAGE"
    assert isinstance(ExpenseType.PEAGE, str)


def test_unknown_label_rejected():
    with pytest.raises(ValueError):
        ExpenseType("UNKNOWN")


def test_names_are_ascii_identifiers():
    for name in ExpenseType.__members__:
        assert name.isascii()
        assert name.isidentifier()
        assert name.isupper()
