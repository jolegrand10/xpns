# CLAUDE.md — Development Guidelines for Xpns #

## Project Overview
Xpns — Expense report automation
See README.md for a full description.

## Python Version
Python 3.10 minimum.

## Philosophy
- **Stdlib first** : prefer Python native libraries over third-party ones.
  Example: `argparse` over `typer`, `logging` over `loguru`.
- Avoid unnecessary complexity. Third-party libraries only when
  the native alternative is clearly insufficient.
- Dynamic typing is a feature, not a bug. No type hints unless
  explicitly requested.

## Language
- All code must be in English: variable names, function names,
  class names, comments, docstrings, log messages.
- French is acceptable only for user-facing text resources
  (prompts, messages, content displayed to end users),
  since the target audience is primarily French-speaking.
- No mixed language in code — if in doubt, use English.

## Communication
Always respond in English.

## Project Structure
- Organized as packages, launched via `python -m package.main`
  or `python -m package.mafonction`.
- No editable install (`pip install -e .` is not used).
- Do not manipulate `sys.path` or `PYTHONPATH`.
  Rely on the project structure instead.
- `tests/` folder for pytest test files.
- `docs/` folder for specs and technical documentation.
- `cli/` folder for command-line interface entry points.

## Version Control
- Local git repository for now; hosting on GitHub is planned for later.
- Do not commit application data to the repository.
- Test data is initialized directly in code, not loaded from files.
- The following must be in `.gitignore`:
  - `.env` and any file containing credentials or API keys
  - `.vscode/`
  - Application data files
  - `__pycache__/`, `.pytest_cache/`, `*.pyc`
  - `*.log`

## Tooling
- **Ruff** is the sole linter and formatter. No autopep8, no flake8, no black.
- **pytest** for all tests, configured via `pytest.ini`.
- Run tests with `python -m pytest` from the project root.

## Testing
- Use `pytest` (not `unittest`, reserved for Django projects).
- Test files in `tests/` folder, named `test_<module>.py`.
- Tests use variables initialized in code — no external data files.
- Tests are seeded from the `main()` function of the corresponding module.

## Module Conventions

Every module — whether it defines a class or a collection
of related functions — follows the same structure:

- A **class module** contains a single class (plus a custom exception
  if needed), named `classe.py` for class `Classe`.
- A **function module** groups functions around a common theme.
- Both types end with a `main()` function protected by
  `if __name__ == "__main__":`, used for interactive smoke testing.

## Testing & Validation Workflow

### Step 1 — main()
When creating or modifying any module, update its `main()`
to demonstrate and exercise the current behavior interactively.
Run it and confirm the output before proceeding.

### Step 2 — tests/
Once main() is validated, reflect the changes in:
- `tests/test_<classname>.py` for a class module
- `tests/test_<funcmodule>.py` for a function module

Do not touch `tests/` before `main()` is validated.

## Logging
- `main()` functions set up logging via a `setup_logger()` call.
- Every module imports `logging` and initializes:
  `logger = logging.getLogger(__name__)`
- Prefer `logger.debug()` and `logger.info()` over `print()`.
- `input()` and `print()` reserved for `main()` or `demo()` functions only,
  and used sparingly.
- Use lazy `%s` formatting in logging calls, never f-strings:
  `logger.info("Login failed for user %s", username)`.
  The message is then built only if actually emitted, formatting errors
  are handled by `logging` instead of crashing the caller, and the
  message template stays intact for filtering and grouping.
  Enforced by Ruff rule `G004`. f-strings remain fine everywhere else.

## Docstrings
- Modules, functions, classes and non-obvious methods get docstrings.
- Module docstring format:
  - For a class module: `"""Module classe.py - home of class Classe"""`
  - For a function module: `"""Module funcmodule.py - home of functions for <theme>"""`