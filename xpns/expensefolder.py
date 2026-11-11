"""Module expensefolder.py - home of functions for building an expense report
from a monthly folder"""

import datetime
import logging
import re
import tempfile
from decimal import Decimal
from pathlib import Path

from xpns.expense import Expense
from xpns.expensetype import ExpenseType

logger = logging.getLogger(__name__)

# Monthly folders are named YYYY-MM.
FOLDER_NAME = re.compile(r"(\d{4})-(\d{2})")
FRENCH_MONTHS = (
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
)
MEMO = "Rapport construit par Xpns"

# File names: "Date core Amount1 [Amount2].pdf"
EXPENSE_SUFFIX = ".pdf"
# YYYY-MM-DD, or YYYY-MM meaning the 1st of the month.
DATE_TOKEN = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")
# nnnEdd or nnnEURdd in euros, nnnXXXdd in another currency (e.g. 123USD45).
AMOUNT_TOKEN = re.compile(r"(\d+)(E|[A-Z]{3})(\d{2})")
EURO_MARKS = {"E", "EUR"}


def my_remove(items, item):
    """Return a copy of items without the first occurrence of item."""
    items = items.copy()
    items.remove(item)
    return items


def half(amount):
    """Return half of amount, rounded to the cent (banker's rounding)."""
    return round(amount / 2, 2)


def parse_folder_name(name):
    """Return (year, month) as integers from a YYYY-MM folder name.

    Raises ValueError if the name does not follow the pattern or the
    month is not between 01 and 12.
    """
    match = FOLDER_NAME.fullmatch(name)
    if not match:
        raise ValueError(f"Folder name must be YYYY-MM: {name!r}")
    year, month = int(match[1]), int(match[2])
    if not 1 <= month <= 12:
        raise ValueError(f"Invalid month in folder name: {name!r}")
    return year, month


def report_subject(year, month):
    """Return the French subject of the report, e.g. "Frais d'Octobre 2026".

    "de" becomes "d'" before a month starting with a vowel
    (Avril, Août, Octobre).
    """
    month_name = FRENCH_MONTHS[month - 1]
    preposition = "d'" if month_name[0] in "AEIOU" else "de "
    return f"Frais {preposition}{month_name} {year}"


def tokenize(name):
    """Split a file name (without extension) into tokens.

    Tokens are separated by spaces, and "@" is always a token of its own:
    "Dej @chez Paul" and "Dej@chez Paul" both give Dej, @, chez, Paul.
    """
    tokens = []
    for word in name.split():
        tokens.extend(part for part in re.split(r"(@)", word) if part)
    return tokens


def parse_date(token):
    """Return the datetime.date of a YYYY-MM-DD or YYYY-MM token.

    Raises ValueError if the token is not a valid date.
    """
    match = DATE_TOKEN.fullmatch(token)
    if not match:
        raise ValueError(f"No date YYYY-MM-DD at the start of the name: {token!r}")
    year, month, day = int(match[1]), int(match[2]), int(match[3] or 1)
    try:
        return datetime.date(year, month, day)
    except ValueError as exc:
        raise ValueError(f"Invalid date {token!r}: {exc}") from None


def split_amounts(tokens):
    """Split the trailing amounts off a list of tokens.

    Up to two amounts are read from the right. Returns (rest, amount) where
    amount is the Decimal amount in euros. Raises ValueError if there is no
    amount in euros or more than one.
    """
    rest = list(tokens)
    euros = []
    for _ in range(2):
        match = AMOUNT_TOKEN.fullmatch(rest[-1]) if rest else None
        if not match:
            break
        rest.pop()
        if match[2] in EURO_MARKS:
            euros.append(Decimal(f"{match[1]}.{match[3]}"))
    if not euros:
        raise ValueError("No amount in euros (nnnEdd or nnnEURdd) at the end")
    if len(euros) > 1:
        raise ValueError(f"More than one amount in euros: {euros[1]} and {euros[0]}")
    return rest, euros[0]


def apply_core_rules(core, amount):
    """Apply the naming rules to the core tokens (between date and amounts).

    Returns (subject, supplier, expense_type, amount). expense_type is None
    when no rule identifies it; amount may be halved by a rule.
    """
    # Habits inherited from the past: the first matching case wins.
    match core:
        case ["AWS"]:
            return "Hébergement applicatif", "AWS", ExpenseType.HEBERGEMENT_WEB, amount
        case _ if "OVH" in core:
            subject = " ".join(my_remove(core, "OVH"))
            return subject, "OVH", ExpenseType.HEBERGEMENT_WEB, amount
        case ["Navigo"] | ["Pass", "Navigo", *_]:
            return "Pass Navigo", "Agence Navigo", ExpenseType.DEPLACEMENT, amount
        case ["Orange", "Fixe" | "Internet", *_]:
            return (
                "(1/2)*@",
                "Orange",
                ExpenseType.INTERNET_ET_TELEPHONE,
                half(amount),
            )
        case ["Orange", "Mobile", *_]:
            return (
                "(1/2)*tel",
                "Orange",
                ExpenseType.INTERNET_ET_TELEPHONE,
                half(amount),
            )
        case ["Dej"]:
            # Missing restaurant name
            return "Déjeuner", "", ExpenseType.REPAS_SEUL, amount

    # Standard rule: "subject @ supplier", or "supplier subject".
    if "@" in core:
        at = core.index("@")
        subject = " ".join(core[:at])
        supplier = " ".join(core[at + 1 :])
    else:
        supplier = core[0] if core else ""
        subject = " ".join(core[1:])

    # Expense type refinements, in this order: the last matching one wins.
    expense_type = None
    if subject == "Dej":
        subject = "Déjeuner"
        expense_type = ExpenseType.REPAS_SEUL
    if supplier in {"Amazon", "Amzn", "Pearl", "LDLC"}:
        expense_type = ExpenseType.ACHATS_PETITS_EQUIPEMENTS
    if supplier in {"4Team", "4TeamCorp", "Cleverbridge"}:
        expense_type = ExpenseType.LOGICIELS
    if subject in {"Mindmanager", "Sync2"}:
        expense_type = ExpenseType.LOGICIELS
    if supplier == "Orange":
        # Former single bill for both fixed line and mobile.
        subject = "(1/2)*(@ + tel)"
        amount = half(amount)
        expense_type = ExpenseType.INTERNET_ET_TELEPHONE
    if supplier in {"Medium"}:
        expense_type = ExpenseType.DOCUMENTATION
    if "Livre" in core:
        expense_type = ExpenseType.DOCUMENTATION
    return subject, supplier, expense_type, amount


def expense_file(file):
    """Return the Expense described by a file name, or None to discard it.

    Non-PDF files are discarded (INFO). A missing subject or supplier is
    logged as a WARNING and left empty. Raises ValueError when critical
    information is missing: date, amount in euros or expense type.
    Only the name is read, the file content is not opened.
    """
    file = Path(file)
    if file.suffix.lower() != EXPENSE_SUFFIX:
        logger.info("Present but not processed (not a PDF): %s", file.name)
        return None

    tokens = tokenize(file.stem)
    if not tokens:
        raise ValueError("Empty name")
    date = parse_date(tokens[0])
    core, amount = split_amounts(tokens[1:])
    subject, supplier, expense_type, amount = apply_core_rules(core, amount)
    if expense_type is None:
        raise ValueError(
            f"No expense type found for subject {subject!r} and supplier "
            f"{supplier!r}: please rename the file"
        )

    for field, value in (("subject", subject), ("supplier", supplier)):
        if not value:
            logger.warning("Missing %s, left empty: %s", field, file.name)
    expense = Expense(
        type=expense_type,
        date=date,
        amount=amount,
        subject=subject,
        supplier=supplier,
        file=file.name,
    )
    logger.info(
        "Accepted: %s -> %s, %s, %s, %r, %r",
        file.name,
        expense.type.name,
        expense.form_date,
        expense.form_amount,
        expense.subject,
        expense.supplier,
    )
    return expense


def analyze_files(folder):
    """Analyze every file of a folder and return (expenses, errors).

    Files are processed in alphabetical order, which is date order since
    their names start with an ISO date. Subfolders are skipped. expenses
    is the list of accepted Expense objects; errors is a list of
    "file name: reason" strings for files lacking critical information.
    Raises ValueError if the folder has no file.
    """
    files = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name):
        if path.is_file():
            files.append(path)
        else:
            logger.info("Present but not processed (subfolder): %s", path.name)
    if not files:
        raise ValueError(f"No file in folder: {folder}")

    expenses = []
    errors = []
    for path in files:
        try:
            expense = expense_file(path)
        except ValueError as exc:
            logger.error("Rejected: %s: %s", path.name, exc)
            errors.append(f"{path.name}: {exc}")
            continue
        if expense is not None:
            expenses.append(expense)
    logger.info(
        "Folder %s: %s file(s), %s expense(s), %s error(s)",
        folder.name,
        len(files),
        len(expenses),
        len(errors),
    )
    return expenses, errors


def folder_report(folder, today=None):
    """Analyze a monthly folder and return (report, errors), without raising
    on file errors, so that the caller can display both.

    report is the dict described in expense_folder, built from the
    accepted files only; errors is the list of "file name: reason"
    strings (see analyze_files). Raises ValueError if the folder is
    missing, badly named or has no file.
    """
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f"Not a folder: {folder}")
    year, month = parse_folder_name(folder.name)
    expenses, errors = analyze_files(folder)
    report = {
        "date": today or datetime.date.today(),
        "subject": report_subject(year, month),
        "memo": MEMO,
        "expenses": expenses,
    }
    return report, errors


def expense_folder(folder, today=None):
    """Build the data of an expense report from a monthly folder.

    The folder must be named YYYY-MM. Every file is analyzed and logged
    (see analyze_files); if any file lacks critical information, a single
    ValueError lists them all, so that no report is built from an
    incomplete folder.

    Returns a dict with the keys expected by louty.fill_expense_report:
    - date: today (or the given today), a datetime.date
    - subject: e.g. "Frais d'Octobre 2026", from the folder name
    - memo: a standard text
    - expenses: the list of Expense objects built from the files
    Raises ValueError if the folder is missing, badly named, has no file
    or no expense, or contains files with critical errors.
    """
    folder = Path(folder).resolve()
    report, errors = folder_report(folder, today)
    if errors:
        raise ValueError(
            f"{len(errors)} file(s) to rename in {folder}:\n" + "\n".join(errors)
        )
    if not report["expenses"]:
        raise ValueError(f"No expense in folder: {folder}")
    return report


def print_expenses(expenses):
    """Print expenses as a table, with their total."""
    print(
        f"{'Date':10}  {'Type':26}  {'Montant':>9}  {'Objet':25}  "
        f"{'Fournisseur':15}  Fichier"
    )
    for e in expenses:
        print(
            f"{e.form_date:10}  {e.type.name[:26]:26}  {e.form_amount:>9}  "
            f"{e.subject[:25]:25}  {e.supplier[:15]:15}  {e.file}"
        )
    total = sum(e.amount for e in expenses)
    print(f"{len(expenses)} expense(s), total {total:.2f}".replace(".", ","))


def pick_folder(initial_dir):
    """Open a folder selection dialog; return the chosen Path, or None."""
    import tkinter
    from tkinter import filedialog

    root = tkinter.Tk()
    root.withdraw()
    # Keep the dialog in front of the editor or terminal.
    root.attributes("-topmost", True)
    chosen = filedialog.askdirectory(
        parent=root,
        initialdir=initial_dir,
        title="Dossier mensuel de frais (YYYY-MM)",
        mustexist=True,
    )
    root.destroy()
    return Path(chosen) if chosen else None


def demo():
    """Built-in examples: subjects, file name rules, a real folder, rejected folders."""
    from xpns.logsetup import setup_logger

    setup_logger(logging.DEBUG)
    for month in range(1, 13):
        logger.info("2026-%02d -> %s", month, report_subject(2026, month))

    print("--- File names ---")
    names = [
        "2026-10-01 AWS 33E31.pdf",
        "2026-10-02 OVH Serveur dédié 12E00.pdf",
        "2026-10-03 Domaine OVH Mail 2E40 3USD10.pdf",
        "2026-10 Navigo 86E40.pdf",
        "2026-10-04 Pass Navigo Octobre 86E40.pdf",
        "2026-10-05 Orange Fixe 33E31.pdf",
        "2026-10-06 Orange Mobile 20E00.PDF",
        "2026-10-07 Orange 60E00.pdf",
        "2026-10-08 Dej 15E50.pdf",
        "2026-10-09 Dej @ chez Paul 18EUR00.pdf",
        "2026-10-10 Câble USB@Amazon 9E99.pdf",
        "2026-10-11 Livre Python @ Amazon 39E90 45USD00.pdf",
        "2026-10-12 Cleverbridge 49E00.pdf",
        "2026-10-13 Corel Mindmanager 99E00.pdf",
        "2026-10-14 Medium 5E00.pdf",
        "2026-10-15 Facture.docx",
        "2026-10-16 Capture.png",
        # critical errors
        "Navigo 86E40.pdf",
        "2026-02-30 Navigo 86E40.pdf",
        "2026-10-17 Navigo.pdf",
        "2026-10-18 Navigo 86E4.pdf",
        "2026-10-19 Navigo 86USD40.pdf",
        "2026-10-20 Navigo 86E40 12EUR00.pdf",
        "2026-10-21 Dej chez Paul 18E00.pdf",
        "2026-10-22 Fnac 25E00.pdf",
    ]
    for name in names:
        try:
            expense_file(Path(name))
        except ValueError as exc:
            logger.error("Rejected: %s: %s", name, exc)

    print("--- Real folder ---")
    folder = Path(__file__).resolve().parent.parent / "data" / "Frais" / "2026-10"
    report = expense_folder(folder)
    for key, value in report.items():
        logger.info("%-8s %r", key, value)

    print("--- Rejected folders ---")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for name in ["2026-13", "Octobre"]:
            (tmp / name).mkdir()
        (tmp / "2026-11").mkdir()
        mixed = tmp / "2026-12"
        mixed.mkdir()
        for name in ["2026-12-01 AWS 33E31.pdf", "2026-12-02 Fnac 25E00.pdf"]:
            (mixed / name).touch()
        (mixed / "notes.txt").touch()
        (mixed / "old").mkdir()
        for path in [tmp / "2026-13", tmp / "Octobre", tmp / "2026-11", mixed]:
            try:
                expense_folder(path)
            except ValueError as exc:
                logger.info("Folder rejected: %s", exc)


def main():
    """Interactive test on real folders: pick a monthly folder in a dialog,
    analyze it and display the expenses found and the files rejected.
    Repeats until the dialog is cancelled.
    """
    from xpns.logsetup import setup_logger

    setup_logger(logging.INFO)
    initial_dir = Path(__file__).resolve().parent.parent / "data" / "Frais"
    while True:
        folder = pick_folder(initial_dir)
        if folder is None:
            print("No folder chosen, end.")
            return
        initial_dir = folder.parent
        print(f"\n=== {folder} ===")
        try:
            year, month = parse_folder_name(folder.name)
            print(f"Subject: {report_subject(year, month)}")
        except ValueError as exc:
            print(f"Folder name: {exc}")
        try:
            expenses, errors = analyze_files(folder)
        except ValueError as exc:
            print(exc)
            continue
        print()
        print_expenses(expenses)
        if errors:
            print(f"\n{len(errors)} file(s) to rename:")
            for error in errors:
                print(f"  {error}")


if __name__ == "__main__":
    main()
