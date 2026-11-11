"""Module main.py - home of functions for the command-line entry point"""

import argparse
import getpass
import logging
import sys
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from xpns import louty
from xpns.expensefolder import folder_report, pick_folder, print_expenses
from xpns.logsetup import LOG_DIR, setup_logger

logger = logging.getLogger(__name__)

YES_ANSWERS = {"o", "oui"}


def parse_args(argv=None):
    """Parse the command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="python -m cli.main",
        description=(
            "Build an expense report from a monthly folder (YYYY-MM) and, "
            "once confirmed, save it as a draft on Louty."
        ),
    )
    parser.add_argument(
        "folder",
        nargs="?",
        help="monthly folder; if omitted, a folder selection dialog opens",
    )
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    return parser.parse_args(argv)


def choose_folder(folder_arg, data_dir):
    """Return the monthly folder: from the command line, or from a dialog
    opened in data_dir (or the home folder). None if the dialog is cancelled.
    """
    if folder_arg:
        return Path(folder_arg)
    initial_dir = Path(data_dir) if data_dir else Path.home()
    if not initial_dir.is_dir():
        logger.warning("XPNS_DATA_DIR not found, dialog opens in home: %s", data_dir)
        initial_dir = Path.home()
    return pick_folder(initial_dir)


def diagnose(folder):
    """Analyze the folder and print the report data and the diagnostics.

    Returns the report dict if Louty can be updated, None otherwise
    (bad folder, files to rename or no expense).
    """
    print(f"\n=== {folder} ===")
    try:
        report, errors = folder_report(folder)
    except ValueError as exc:
        print(f"\n{exc}")
        return None
    print(f"Objet : {report['subject']}")
    print(f"Date  : {report['date']:%d/%m/%Y}\n")
    print_expenses(report["expenses"])
    if errors:
        print(f"\n{len(errors)} fichier(s) à renommer :")
        for error in errors:
            print(f"  {error}")
        print("\nCorriger les noms de fichiers puis relancer Xpns.")
        return None
    if not report["expenses"]:
        print("\nAucune dépense dans ce dossier.")
        return None
    return report


def update_louty(settings, username, password, folder, report, headed):
    """Create the expense report on Louty: fill it, attach files, save it.

    Takes a screenshot at the end, of the failed step or of the saved
    report. Returns True if the report was saved.
    """
    success = False
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        page = browser.new_page()
        try:
            step = "login"
            success = louty.login(page, settings["url"], username, password)
            if success:
                step = "expense_form"
                frame = louty.open_new_expense_report(page)
                success = frame is not None and louty.check_expense_form(frame)
            if success:
                step = "fill"
                success = louty.fill_expense_report(frame, **report)
            if success:
                step = "files"
                success = louty.attach_files(frame, folder, report["expenses"])
            if success:
                step = "save"
                success = louty.save_expense_report(frame)
            name = f"note_{folder.name}.png" if success else f"{step}_failure.png"
            screenshot = LOG_DIR / name
            page.screenshot(path=screenshot, full_page=True)
            logger.info("Screenshot: %s", screenshot)
        except PlaywrightError:
            logger.exception("Browser automation error at step %s", step)
            success = False
        finally:
            browser.close()
    return success


def main(argv=None):
    """Build the expense report of a monthly folder and, if the folder is
    clean and the user confirms, save it as a draft on Louty.

    Returns the process exit code: 0 if the report was saved or the user
    declined, 1 if the folder needs corrections or Louty failed.
    """
    args = parse_args(argv)
    setup_logger(logging.DEBUG if args.debug else logging.INFO)
    settings = louty.load_settings()

    folder = choose_folder(args.folder, settings["data_dir"])
    if folder is None:
        print("Aucun dossier choisi.")
        return 0
    folder = folder.resolve()
    report = diagnose(folder)
    if report is None:
        return 1

    answer = input("\nMettre à jour Louty avec cette note de frais ? (oui/non) : ")
    if answer.strip().lower() not in YES_ANSWERS:
        print("Louty n'a pas été modifié.")
        return 0

    username = settings["username"] or input("Louty username: ")
    password = settings["password"] or getpass.getpass("Louty password: ")
    if update_louty(settings, username, password, folder, report, args.headed):
        print(f"\nNote enregistrée en brouillon : {report['subject']}")
        print("À vérifier sur Louty, puis « Sauvegarder et transmettre ».")
        return 0
    print("\nÉchec de la mise à jour de Louty : voir le journal et la capture.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
