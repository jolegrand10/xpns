"""Module expensetype.py - home of class ExpenseType"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ExpenseType(str, Enum):
    """Expense types offered in the expense form's combo box.

    Each value is the exact label displayed on screen, typos included
    (e.g. the doubled parenthesis, the truncated "energ"), so it can be
    passed as-is to Playwright. Member names are cleaned-up identifiers.
    """

    ACHAT_MARCHANDISES_REVENTE = "ACHAT MARCHANDISES (Revente)"
    ACHATS_INTRACOMMUNAUTAIRE = "ACHATS (intracommunautaire))"
    ACHATS_PETITS_EQUIPEMENTS = "ACHATS (petits équipements)"
    CADEAUX_A_LA_CLIENTELE = "CADEAUX A LA CLIENTELE"
    COMMUNICATION = "COMMUNICATION"
    DEPLACEMENT = "DEPLACEMENT"
    DOCUMENTATION = "DOCUMENTATION"
    ENTRETIEN = "ENTRETIEN"
    FORMATION = "FORMATION"
    FOURNISSEUR = "FOURNISSEUR"
    FOURNITURE_NON_STOCKABLE_ENERGIE = "FOURNITURE NON STOCKABLE energ"
    FOURNITURES_DE_BUREAU = "FOURNITURES DE BUREAU"
    FRAIS_DE_MISSION = "FRAIS DE MISSION"
    FRAIS_POSTAUX = "FRAIS POSTAUX"
    HEBERGEMENT_WEB = "HEBERGEMENT WEB"
    HONORAIRES = "HONORAIRES"
    HOTEL = "HOTEL"
    INTERNET_ET_TELEPHONE = "Internet et téléphone (50 %)"
    LOCATION_IMMOBILIERE = "LOCATION IMMOBILIERE"
    LOCATION_MOBILIERE = "LOCATION MOBILIERE"
    LOGICIELS = "LOGICIELS"
    PEAGE = "PEAGE"
    PRESSE = "PRESSE"
    PUBLICATION = "PUBLICATION"
    RECEPTIONS = "RECEPTIONS"
    REPAS_INVITATION = "REPAS INVITATION"
    REPAS_SEUL = "REPAS SEUL"
    TRANSPORT = "TRANSPORT"

    def __str__(self):
        return self.value


def main():
    """Smoke test: list all members and exercise label lookup."""
    from xpns.logsetup import setup_logger

    setup_logger()
    for expense_type in ExpenseType:
        logger.info("%-34s -> %r", expense_type.name, expense_type.value)
    logger.info("Count: %s", len(ExpenseType))

    label = "ACHATS (intracommunautaire))"
    logger.info("Lookup %r -> %s", label, ExpenseType(label).name)
    logger.info("str() gives label: %s", ExpenseType.HOTEL)
    logger.info("Equal to plain string: %s", ExpenseType.PEAGE == "PEAGE")
    try:
        ExpenseType("UNKNOWN")
    except ValueError as exc:
        logger.info("Unknown label rejected: %s", exc)


if __name__ == "__main__":
    main()
