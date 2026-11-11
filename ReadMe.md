# Xpns #

Automate the monthly expense report process.

Using Playwright and Chromium.

Use also dotenv for config params and sensitive data.

# Environment set-up
Core:
- `playwright`
- `python-dotenv`

and for dev:
- `pytest`
- `ruff`

`python -m playwright install chromium` is required after `pip install playwright` and again, after any upgrade.

## Installation (Windows)

From the project folder:

```
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m playwright install chromium
```

For development, add `venv\Scripts\python.exe -m pip install -r requirements-dev.txt`.

Then copy `.env.example` to `.env` and fill it in:

| Variable | Meaning |
|---|---|
| `LOUTY_URL` | Louty application URL (default provided) |
| `LOUTY_USERNAME`, `LOUTY_PASSWORD` | Louty credentials; asked at run time if missing |
| `XPNS_DATA_DIR` | folder holding the monthly folders (`YYYY-MM`); the folder dialog opens there. Optional: defaults to the home folder |

`.env` holds credentials: it is ignored by git and must never be committed.

# Usage

Double-click `xpns.bat`, or a desktop shortcut pointing to it (right-click `xpns.bat` > Send to > Desktop). From a command prompt:

```
xpns.bat [folder] [--headed] [--debug]
```

- `folder`: the monthly folder to process. If omitted, a folder dialog opens in `XPNS_DATA_DIR`.
- `--headed`: show the browser window while Louty is updated.
- `--debug`: verbose logging.

Xpns then:

1. Analyzes every file of the folder and displays the report subject, a table of the expenses with their total, and diagnostics in the log: INFO for files present but not processed, WARNING for a missing subject or supplier, ERROR for a missing date, euro amount or expense type.
2. If any file must be renamed, lists them and stops without touching Louty. Rename the files and run Xpns again.
3. Otherwise, asks "Mettre à jour Louty avec cette note de frais ? (oui/non)".
   - `non`: stops, Louty is not modified.
   - `oui`: logs in to Louty, creates a new expense report, fills its header and one line per expense, attaches the PDF files and saves it as a draft (Brouillon). A screenshot is saved to `logs/note_<YYYY-MM>.png`.

The draft is then checked, edited or deleted manually on Louty; "Sauvegarder et transmettre", signature and email are outside the scope of Xpns.

Exit code: 0 if the report was saved or the update declined, 1 if the folder needs corrections or Louty failed (a screenshot `logs/<step>_failure.png` shows the failed step). The log of every run is in `logs/xpns.log`.

# Expense report process

- Collect input data (invoices, paid bills, mostly made of PDF files with standard naming rules) in an input folder.
This is a separate function to be located in xpns. It does not need to interact with Louty. Its role is to analyze the input folder and build the data that will be entered in the form, in the next step, already available. The signature of the function is

```python
def expense_folder(folder:Path)->Tuple(date, subject, memo, expenses,):
  pass 
```

The date should be today. In the format expected by Louty, ie DD/MM/YYYY

The subject should be inferred from the name of the folder. Folders are named after the months because the expense report process runs once and monthly. The name of a folder is YYYY-MM.  This name should be translated to a title in French. As an example, "2026-10" should give "Frais d'Octobre 2026". The year and the month should be isolated. The month number should be translated to its french name, capitalized. Also for Avril, Août and Octobre, it is necessary to use "d'" instead of "de". We write "Frais de Septembre 2026" for 2026-09 but "Frais d'Octobre 2026" for 2026-10.

The memo field is made of a standard text : "Rapport construit par Xpns".


The folder is scanned and each file is analyzed. The same function is applied to each file found. Its signature is
```python
def expense_file(file:Path)-> Option(Expense):
  pass 
```

The expense objects returned by this functions will be stored in a list that will be returned by the expense_folder function (among other items).

## Files
Files under consideration are .PDF files.

Non PDF files are discarded and a Warning is logged.

## Lexical level / Scanning

Split the name into a list of tokens using space as a separator.
```
a b c --> a,b,c
```
Split further the tokens that contain an "@" =, with a rule like
```
a@b --> a, @, b
```

## Syntactic analysis / parsing

### Structure

```
Filename  = Date-ISO  core AmountCurrency1 AmountCurrency2.pdf
```

Attack the list from the left to decode the date from the very first token

#### Date
Rules for date:
- Date is a prefix to all names.
- Date starts at the beginning of the name and ends at the space char.
- Date is presented in the ISO format, "YYYY-MM-DD".
- In case -DD is missing, -01 is assumed.
- If no match, raise an exception and discard the current file

#### Amount
Attack next the list from the right to decode the amount

Rules for amount:
- Amount may be in Euros, but also in another currency
- We are interested by the amount in Euros only
- Amount in Euros is written as nnnEdd ; this represents a decimal number nnn.dd - the decimal mark is replaced by letter "E" 
- Amount in Euros may sometimes also use the 3 letters "EUR" as in nnnEURdd
- Amount in another currency uses the standard currency acronym in 3 letters. Such amounts appear as e.g. 123USD45.

If either Date or Amount is missing,  the file should be discarded and a message logged (warning level)

#### Core

```
core = [subject [@] ] supplier
```




```python
subject= ""
supplier = ""

# the following are habits and straightfoward cases
# inherited from the past
if token[0]=="AWS" and len(token)==1:
  subject="Hébergement applicatif"
  supplier = "AWS"
  expense_type= "HEBERGEMENT WEB"
  return

if "OVH" in token:
  supplier="OVH"
  subject=" ".join(my_remove(token, "OVH"))
  expense_type= "HEBERGEMENT WEB"
  return

if token[0]=="Navigo" and len(token)==1:
  subject="Pass Navigo"
  supplier="Agence Navigo"
  expense_type= "DEPLACEMENT"
  return

if token[0]=="Pass" and token[1]=="Navigo":
  subject="Pass Navigo"
  supplier="Agence Navigo"
  expense_type= "DEPLACEMENT"
  return

if token[0]=="Orange" and  token[1] in {"Fixe" ,"Internet"}:
  supplier = "Orange"
  subject="(1/2)*@" 
  amount = round(amount/2, 2)
  expense_type= "Internet et téléphone(50 %)"
  return

if token[0]=="Orange" and token[1] == "Mobile":
  supplier = "Orange"
  subject="(1/2)*tel" 
  amount = round(amount/2, 2)
  expense_type= "Internet et téléphone(50 %)"
  return

if token[0]=="Dej" and len(token)==1:
  subject="Déjeuner"
  supplier = "" # Missing restaurant address
  expense_type= "REPAS SEUL"
  return

# this is the standard rule to be followed in the future
if "@" in token:
  subject = " ".join(token[:token.index("@")])
  supplier = " ".join(token[token.index("@")+1:])
elif len(token)>=1:
  supplier = token[0]
  subject = " ".join(token[1:])



if subject=="Dej":
  subject="Déjeuner"
  expense_type= "REPAS SEUL"

if supplier in {'Amazon', 'Amzn', 'Pearl', 'LDLC'}:
  expense_type="ACHATS (petits équipements)"

if supplier in {'4Team', '4TeamCorp', 'Cleverbridge'}:
  expense_type="LOGICIELS"

if subject in {'Mindmanager', 'Sync2'}:
  expense_type="LOGICIELS"

if supplier == "Orange":
  subject="(1/2)*(@ + tel)" 
  amount = round(amount/2, 2)
  expense_type= "Internet et téléphone (50 %)"

if supplier in {'Medium'}:
  expense_type="DOCUMENTATION"

if "Livre" in token:
  expense_type="DOCUMENTATION"
```

- Open the application page at https://appli.louty.net/Louty/content

- Enter username/password info to connect (username/password info to be provided in an external env file managed with dotenv)

- Connect to the home page


- enter the expense report page following the detailed path below
  - From the home page, in its left column dedicated to the applications and entitled "MES APPLICATIONS" find "Note de Frais" combo box
  - Open the combo box. Among the choices offered, select and click on the "plus" sign ("+") to create a new "note de frais" (ie "expense report"). As an alternate path, follow "Autres actions" : a new content displayed in the core of the page will show possible actions. One of them is "Nouvelle note de frais".
  - Create a "Note de frais" opens a new content in the core of the page. That's the form we need to fill to create a note de frais.
  - We are interested in the fields named Date, Objet, the tab entitled "Lignes", the tab entitled "Fichiers" and their content, the buttons named Enregistrer (combo box)
  - If everything is found mention it in logger.debug messages, return success and we should be ready to enter data. This will be our next step. If something is missing mention it in the log (Debug messages). Issue an INFO message to advise success or failure.
- Create classes for ExpenseType and Expense, paste a list of expenses in the expense form, attach the related bills and save the expense report, leaving to the user the possibility to discard it, correct it and possibly use it in the further steps of the expense process.

Possible remaining steps - not envisaged at the moment
- print
- send
- save report in PDF
- sign report (paste signature)
- attach signed report to a mail
- send email



  
# Code structure

* **`xpns.bat`**: the Windows launcher. It moves to its own folder, switches the console to UTF-8, checks that `venv` exists (otherwise it prints the installation commands) and runs `python -m cli.main`, passing its arguments on. It pauses at the end so the window stays open.

* **`cli/main.py`**: the entry point, run with `python -m cli.main` (see Usage). `choose_folder()` takes the folder from the command line or from the dialog, `diagnose()` analyzes it and prints the table and the files to rename, and `update_louty()` runs the Louty steps once the user has answered `oui`. If the username or password is missing from `.env`, it asks for them, hiding the password as you type.

* **`xpns/expensefolder.py`**: builds the report from a monthly folder, without Louty. `expense_file()` applies the file naming rules (date, amounts, core rules with `match`, expense type refinements) and returns an `Expense`, `None` for a file to discard, or raises `ValueError` for missing critical information. `analyze_files()` processes every file of a folder in alphabetical (date) order and collects the errors; `folder_report()` adds the report date, subject ("Frais d'Octobre 2026") and memo; `expense_folder()` does the same but raises if any file must be renamed. Run `python -m xpns.expensefolder` to analyze folders picked in a dialog and display their expenses, without Louty.

* **`xpns/louty.py`**: the Louty logic. `load_settings()` reads `.env`, `login()` logs in, `open_new_expense_report()` opens a new report from the left menu and `check_expense_form()` checks the form. `fill_expense_report()` fills the header (Mémo, Date, Objet) and adds one validated line per expense with `fill_line()`; `attach_files()` uploads each expense's PDF in the Fichiers tab with the description "Subject - Supplier"; `save_expense_report()` clicks Enregistrer. The form is a legacy page embedded in an iframe, so its elements are reached through a frame locator. Each typed value is checked, and filling a line waits for the form's background requests to finish (picking a type triggers `UpdateTypAchat` then `AddLigne`, which resets the row). `python -m xpns.louty` runs a flagged test report ("Ceci est un test", amounts 0,01) and saves it only if `oui` is typed.

* **`xpns/expense.py`**: the `Expense` frozen dataclass. It converts and validates its fields (type, date, amount as `Decimal`, file path) and gives the values as typed in the form (`form_date`, `form_amount`).

* **`xpns/expensetype.py`**: the `ExpenseType` enum. Its values are the exact labels of Louty's "Type d'achat" list, typos included.

* **`xpns/logsetup.py`**: `setup_logger()`, which logs to the console and to `logs/xpns.log`. Git ignores that file.

* **`tests/`**: pytest tests (`python -m pytest`), one file per module. The CLI tests replace Louty, the folder dialog and `.env` with stand-ins, so the test suite never opens a browser.
