"""Module louty.py - home of functions for the Louty web application"""

import datetime
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect, sync_playwright

from xpns.expense import DATE_FORMAT, Expense
from xpns.logsetup import LOG_DIR, setup_logger

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://appli.louty.net/Louty/content"
# Louty is an Angular app: while not authenticated, the URL holds this outlet.
LOGIN_URL_MARKER = "loginOutlet:login"
LOGIN_FORM = "form:has(input[formcontrolname='username'])"
ERROR_SELECTOR = ".alert, .text-danger, .invalid-feedback, .toast-body, [role='alert']"
TIMEOUT_MS = 15000

# Left menu, "MES APPLICATIONS" column: group label and its "+" icon.
EXPENSE_GROUP_LABEL = ".menuPanelGroupLabel[title='Notes de frais']"
NEW_EXPENSE_ICON = "i.app-menu-panel-action[title='Nouvelle note de frais']"
# The expense report form is a legacy page embedded in an iframe.
EXPENSE_FRAME = "iframe[src*='NoteFraisEdit']"
EXPENSE_FORM_TITLE = "h3:text-is('Nouvelle note de frais')"
EXPENSE_FORM_ITEMS = {
    "Date field": "#noteDate",
    "Objet field": "#titre",
    "Lignes tab": "#tabNoteFrais a[href='#lignes']",
    "Fichiers tab": "#tabFichiers",
    "Enregistrer button": "#btnEnregistrerHaut",
    "Enregistrer menu toggle": "#mnuEnregistrerHaut",
}

# Expense report header fields.
MEMO_FIELD = "#memoInterne"
DATE_FIELD = "#noteDate"
SUBJECT_FIELD = "#titre"
SUBJECT_MAX_LENGTH = 40
LINES_TAB = "#tabNoteFrais a[href='#lignes']"

# "Frais professionnels hors déplacements véhicules particuliers" table.
# Rows have negative ids (nflId_-1, nflId_-2, ...). The last row is always
# the empty input row; validating it appends a new empty row.
LINES_ROWS = "#table_noteFrais tbody tr"
LINE_ROW_PREFIX = "nflId_"
# Per-row fields, formatted with the row number (e.g. "-1").
LINE_TYPE_BUTTON = "#btnTypNflAchat_{}"
LINE_TYPE = "#nflTypAchat_{}"
LINE_DATE = "#nflDate_{}"
LINE_AMOUNT = "#nflMontantHT_{}"
LINE_SUBJECT = "#nflObjet_{}"
LINE_SUPPLIER = "#nflFournisseurLibelle_{}"
LINE_VALIDATE_BUTTON = "#btn_Valid_{}"
LINE_BROWSE_BUTTONS = "#browseBtn_{}"
LINE_SUBJECT_MAX_LENGTH = 40
LINE_SUPPLIER_MAX_LENGTH = 30
# Modal listing the expense types, opened by the row's type button.
TYPE_MODAL = "#modalListeTypAchat"
# Fichiers tab and its "Téléchargement de fichier" upload dialog.
FILES_TAB = "#tabFichiers"
FILES_ROWS = "#tablePieceFichier tbody tr"
ADD_FILE_BUTTON = "#btnAjoutFichier"
FILE_DESCRIPTION = "#inputDescriptionFichier"
FILE_INPUT = "#filePieceUpload"
FILE_NAME = "#inputFichierNom"
FILE_SAVE_BUTTON = "#fichierEnregistrer"
# Save button and report state.
SAVE_BUTTON = "#btnEnregistrerHaut"
STATE_FIELD = "#etat"
# Any open dialog of the form, e.g. "Erreur lors de la validation de la ligne."
ERROR_DIALOG = "#modalPopup"


def load_settings():
    """Load the Louty URL, credentials and data folder from .env and the
    environment.

    Returns a dict with keys url, username, password and data_dir.
    Missing values are None (except url), so the caller decides how to
    obtain them. data_dir (XPNS_DATA_DIR) is the folder holding the
    monthly expense folders.
    """
    load_dotenv()
    settings = {
        "url": os.getenv("LOUTY_URL") or DEFAULT_URL,
        "username": os.getenv("LOUTY_USERNAME") or None,
        "password": os.getenv("LOUTY_PASSWORD") or None,
        "data_dir": os.getenv("XPNS_DATA_DIR") or None,
    }
    logger.debug(
        "Settings: url=%s, username=%s, password %s, data_dir=%s",
        settings["url"],
        settings["username"],
        "set" if settings["password"] else "missing",
        settings["data_dir"],
    )
    return settings


def read_error_message(page):
    """Return the visible error texts of the page joined by ' | ', or ''."""
    texts = []
    for element in page.locator(ERROR_SELECTOR).all():
        if element.is_visible():
            text = element.inner_text().strip()
            if text:
                texts.append(text)
    return " | ".join(texts)


def login(page, url, username, password, timeout_ms=TIMEOUT_MS):
    """Open the Louty application, submit the credentials and check the outcome.

    Success means the app navigated away from the login outlet within
    timeout_ms. Returns True on success, False otherwise.
    """
    logger.info("Opening %s", url)
    page.goto(url)
    form = page.locator(LOGIN_FORM)
    form.locator("input[formcontrolname='username']").fill(username)
    form.locator("input[formcontrolname='password']").fill(password)
    logger.info("Submitting credentials for user %s", username)
    form.get_by_role("button", name="Connexion").click()
    try:
        page.wait_for_url(lambda u: LOGIN_URL_MARKER not in u, timeout=timeout_ms)
    except PlaywrightTimeoutError:
        message = read_error_message(page)
        logger.error(
            "Login failed for user %s: %s",
            username,
            message or "still on the login page, no error message displayed",
        )
        return False
    page.wait_for_load_state("networkidle")
    logger.info("Login succeeded: %s (title: %s)", page.url, page.title())
    return True


def open_new_expense_report(page, timeout_ms=TIMEOUT_MS):
    """From the home page, open the form of a new expense report.

    Expands "Notes de frais" in the left menu and clicks its "+" icon.
    Returns the frame locator of the form, or None if the menu is not found.
    """
    for description, selector in (
        ("Notes de frais menu group", EXPENSE_GROUP_LABEL),
        ("Nouvelle note de frais icon", NEW_EXPENSE_ICON),
    ):
        try:
            page.locator(selector).click(timeout=timeout_ms)
        except PlaywrightTimeoutError:
            logger.debug("Not found: %s (%s)", description, selector)
            logger.info("Cannot open a new expense report")
            return None
        logger.debug("Clicked: %s", description)
    return page.frame_locator(EXPENSE_FRAME)


def check_expense_form(frame, timeout_ms=TIMEOUT_MS):
    """Check that the new expense report form shows the expected elements.

    Nothing is clicked. Waits up to timeout_ms for the form title, then
    checks each item of EXPENSE_FORM_ITEMS. Returns True if all are visible.
    """
    try:
        frame.locator(EXPENSE_FORM_TITLE).wait_for(timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logger.debug("Not found: form title (%s)", EXPENSE_FORM_TITLE)
        logger.info("Expense report form not found")
        return False
    logger.debug("Found: form title 'Nouvelle note de frais'")
    missing = []
    for description, selector in EXPENSE_FORM_ITEMS.items():
        if frame.locator(selector).is_visible():
            logger.debug("Found: %s", description)
        else:
            logger.debug("Not found: %s (%s)", description, selector)
            missing.append(description)
    if missing:
        logger.info("Expense report form incomplete, missing: %s", ", ".join(missing))
        return False
    logger.info("Expense report form ready for data entry")
    return True


def fit(text, max_length, description):
    """Return text cut to max_length, logging a warning if it was too long.

    The form fields silently drop characters beyond their maxlength,
    so cutting here makes the loss visible in the log.
    """
    if len(text) <= max_length:
        return text
    logger.warning(
        "%s cut to %s characters: %r", description, max_length, text[:max_length]
    )
    return text[:max_length]


def fill_checked(field, text, description, timeout_ms=TIMEOUT_MS, date=False):
    """Fill a field and check that it holds text. Returns True on success.

    With date=True, the datepicker calendar is closed after typing.
    """
    field.fill(text)
    if date:
        field.press("Escape")
    try:
        expect(field).to_have_value(text, timeout=timeout_ms)
    except AssertionError:
        logger.error(
            "%s shows %r instead of %r", description, field.input_value(), text
        )
        return False
    return True


def close_error_dialog(frame):
    """Return the text of the form's visible error dialog and close it, or ''."""
    dialog = frame.locator(ERROR_DIALOG)
    if not dialog.is_visible():
        return ""
    message = " ".join(dialog.inner_text().split())
    try:
        dialog.get_by_role("button", name="Fermer").click(timeout=2000)
    except PlaywrightTimeoutError:
        logger.debug("Could not close the error dialog")
    return message


def empty_row_number(frame):
    """Return the number of the empty input row of the lines table, e.g. "-2"."""
    row_id = frame.locator(LINES_ROWS).last.get_attribute("id")
    return row_id.removeprefix(LINE_ROW_PREFIX)


def fill_line(frame, row, expense, timeout_ms=TIMEOUT_MS):
    """Fill row number `row` of the lines table with `expense` and validate it.

    Picks the expense type in the type modal, fills date, amount (H.T.),
    subject and supplier, then clicks "Valider". Returns True if the row
    switched to its validated state, False otherwise.
    """
    label = expense.type.value
    rows = frame.locator(LINES_ROWS)
    count = rows.count()
    frame.locator(LINE_TYPE_BUTTON.format(row)).click(timeout=timeout_ms)
    frame.locator(TYPE_MODAL).get_by_role("link", name=label, exact=True).click(
        timeout=timeout_ms
    )
    # The form sets the type field shortly after the modal closes.
    type_field = frame.locator(LINE_TYPE.format(row))
    try:
        expect(type_field).to_have_value(label, timeout=timeout_ms)
    except AssertionError:
        logger.error(
            "Row %s: type field shows %r instead of %r",
            row,
            type_field.input_value(),
            label,
        )
        return False
    # Picking a type makes the form set up the row in the background
    # (requests UpdateTypAchat, then AddLigne) and values typed meanwhile
    # can be wiped. The last step appends the next empty row: wait for it.
    try:
        expect(rows).to_have_count(count + 1, timeout=timeout_ms)
    except AssertionError:
        logger.error("Row %s: the form did not add the next empty row", row)
        return False

    fields = [
        (LINE_DATE, expense.form_date, "date"),
        (LINE_AMOUNT, expense.form_amount, "amount"),
        (
            LINE_SUBJECT,
            fit(expense.subject, LINE_SUBJECT_MAX_LENGTH, f"Row {row} subject"),
            "subject",
        ),
        (
            LINE_SUPPLIER,
            fit(expense.supplier, LINE_SUPPLIER_MAX_LENGTH, f"Row {row} supplier"),
            "supplier",
        ),
    ]
    for selector, text, name in fields:
        if not fill_checked(
            frame.locator(selector.format(row)),
            text,
            f"Row {row} {name}",
            timeout_ms,
            date=selector == LINE_DATE,
        ):
            return False

    frame.locator(LINE_VALIDATE_BUTTON.format(row)).click(timeout=timeout_ms)
    try:
        frame.locator(LINE_BROWSE_BUTTONS.format(row)).wait_for(timeout=timeout_ms)
    except PlaywrightTimeoutError:
        logger.error(
            "Row %s: not validated by the form: %s",
            row,
            close_error_dialog(frame) or "no error message displayed",
        )
        return False
    logger.info(
        "Row %s validated: %s, %s, %s, %s, %s",
        row,
        label,
        expense.form_date,
        expense.form_amount,
        expense.subject,
        expense.supplier,
    )
    return True


def fill_expense_report(frame, date, subject, memo, expenses, timeout_ms=TIMEOUT_MS):
    """Fill a new expense report form: header fields, then one line per expense.

    date is a datetime.date or a DD/MM/YYYY string. Each expense of the
    list becomes a validated line of the "Frais professionnels hors
    déplacements véhicules particuliers" table. The report is not saved.
    Returns True if every step succeeded; stops at the first failed line.
    """
    if isinstance(date, datetime.date):
        date = date.strftime(DATE_FORMAT)
    else:
        # validate the string; raises ValueError if malformed
        datetime.datetime.strptime(date, DATE_FORMAT)

    subject = fit(subject, SUBJECT_MAX_LENGTH, "Subject")
    for selector, text, name in [
        (MEMO_FIELD, memo, "Memo"),
        (DATE_FIELD, date, "Date"),
        (SUBJECT_FIELD, subject, "Subject"),
    ]:
        field = frame.locator(selector)
        if not fill_checked(field, text, name, timeout_ms, date=name == "Date"):
            logger.info("Expense report filling stopped at the header")
            return False
    logger.info("Header filled: date %s, subject %r", date, subject)

    frame.locator(LINES_TAB).click(timeout=timeout_ms)
    for index, expense in enumerate(expenses, start=1):
        row = empty_row_number(frame)
        logger.debug("Expense %s/%s goes to row %s", index, len(expenses), row)
        if not fill_line(frame, row, expense, timeout_ms):
            logger.info("Expense report filling stopped at expense %s", index)
            return False
    logger.info("Expense report filled with %s line(s), not saved", len(expenses))
    return True


def file_description(expense):
    """Return the description of an expense's file: "Subject - Supplier"."""
    return f"{expense.subject} - {expense.supplier}"


def attach_file(frame, path, description, timeout_ms=TIMEOUT_MS):
    """Upload one file in the Fichiers tab, with its description.

    Clicks "Ajouter un fichier", fills the description, selects the file
    and clicks the dialog's Enregistrer. The "Imprimer ce fichier avec la
    pièce" box is left as is (unticked). Returns True once the file is
    listed in the files table, False otherwise.
    """
    rows = frame.locator(FILES_ROWS)
    count = rows.count()
    frame.locator(ADD_FILE_BUTTON).click(timeout=timeout_ms)
    if not fill_checked(
        frame.locator(FILE_DESCRIPTION), description, "File description", timeout_ms
    ):
        return False
    # The file input is hidden behind a styled button: set it directly,
    # no file selection dialog is opened.
    frame.locator(FILE_INPUT).set_input_files(path)
    try:
        expect(frame.locator(FILE_NAME)).to_have_value(path.name, timeout=timeout_ms)
    except AssertionError:
        logger.error("File %s not taken by the upload dialog", path.name)
        return False

    frame.locator(FILE_SAVE_BUTTON).click(timeout=timeout_ms)
    try:
        expect(rows).to_have_count(count + 1, timeout=timeout_ms)
    except AssertionError:
        logger.error(
            "File %s not added: %s",
            path.name,
            close_error_dialog(frame) or "no error message displayed",
        )
        return False
    logger.info("File attached: %s (%s)", path.name, description)
    return True


def attach_files(frame, folder, expenses, timeout_ms=TIMEOUT_MS):
    """Attach the file of each expense in the Fichiers tab.

    Each expense's file is looked up as folder / expense.file. All files
    are checked before any upload. Returns True if every file was
    attached; stops at the first failure.
    """
    folder = Path(folder)
    paths = [folder / expense.file for expense in expenses]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        logger.error("Missing file(s): %s", ", ".join(missing))
        return False

    frame.locator(FILES_TAB).click(timeout=timeout_ms)
    for index, (expense, path) in enumerate(zip(expenses, paths, strict=True), start=1):
        logger.debug("File %s/%s: %s", index, len(expenses), path)
        if not attach_file(frame, path, file_description(expense), timeout_ms):
            logger.info("File attachment stopped at expense %s", index)
            return False
    logger.info("%s file(s) attached, report not saved", len(paths))
    return True


def save_expense_report(frame, dry_run=False, timeout_ms=TIMEOUT_MS):
    """Save the expense report by clicking the form's Enregistrer button.

    The report stays in the Brouillon state, waiting for a human to print,
    sign and send it. With dry_run=True, only checks that the button could
    be clicked (enabled, visible, not covered) and saves nothing.
    Returns True on success.
    """
    button = frame.locator(SAVE_BUTTON)
    if dry_run:
        try:
            button.click(trial=True, timeout=timeout_ms)
        except PlaywrightTimeoutError:
            logger.error("Dry run: Enregistrer cannot be clicked")
            return False
        logger.info("Dry run: Enregistrer could be clicked, report NOT saved")
        return True

    button.click(timeout=timeout_ms)
    # The button is disabled while the form has no unsaved change.
    try:
        expect(button).to_be_disabled(timeout=timeout_ms)
    except AssertionError:
        logger.error(
            "Expense report not saved: %s",
            close_error_dialog(frame) or "no error message displayed",
        )
        return False
    logger.info(
        "Expense report saved, state: %s",
        frame.locator(STATE_FIELD).input_value(),
    )
    return True


def main():
    """Smoke test: create a complete test expense report on Louty.

    Logs in headless, opens a new expense report, fills it, attaches the
    files from data/Frais/2026-10, then saves it if the user types "oui";
    otherwise it is a dry run and nothing is saved. The report is flagged
    as a test in its Objet and Mémo. A screenshot is written to the logs
    folder.
    """
    setup_logger(logging.DEBUG)
    settings = load_settings()
    if not (settings["username"] and settings["password"]):
        print("LOUTY_USERNAME and LOUTY_PASSWORD must be set in .env")
        return
    expenses = [
        Expense(
            type="DEPLACEMENT",
            date=datetime.date(2026, 10, 1),
            amount="0,01",
            subject="Pass Navigo",
            supplier="Agence Navigo",
            file="2026-01 Pass Navigo 45E40.pdf",
        ),
        Expense(
            type="HEBERGEMENT_WEB",
            date=datetime.date(2026, 10, 1),
            amount="0,01",
            subject="Hébergement applicatif",
            supplier="AWS",
            file="2026-10-01 AWS 33E31.pdf",
        ),
    ]
    folder = Path(__file__).resolve().parent.parent / "data" / "Frais" / "2026-10"
    subject = "Ceci est un test - Frais d'Octobre 2026"
    memo = (
        "Ceci est un test d'automatisation - ne pas tenir compte de cette note de frais"
    )
    print(f"Test expense report: {subject!r}")
    answer = input("Type 'oui' to SAVE it on Louty, Enter for a dry run: ")
    dry_run = answer.strip().lower() != "oui"
    screenshot = LOG_DIR / "expense_report_saved.png"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        success = login(
            page, settings["url"], settings["username"], settings["password"]
        )
        if success:
            frame = open_new_expense_report(page)
            success = frame is not None and check_expense_form(frame)
        if success:
            success = fill_expense_report(
                frame,
                date="09/11/2026",
                subject=subject,
                memo=memo,
                expenses=expenses,
            )
        if success:
            success = attach_files(frame, folder, expenses)
        if success:
            success = save_expense_report(frame, dry_run=dry_run)
        page.screenshot(path=screenshot, full_page=True)
        browser.close()
    if not success:
        print("Failed")
    elif dry_run:
        print("Dry run complete: report filled, NOT saved")
    else:
        print("Expense report saved: check it on Louty")
    print(f"Screenshot: {screenshot}")


if __name__ == "__main__":
    main()
