"""Tests for module cli/main.py - functions for the command-line entry point

Louty, the folder dialog, .env and the logger setup are replaced by
stand-ins: these tests never open a browser nor touch Louty.
"""

from pathlib import Path

import pytest

from cli import main as cli
from xpns import louty

SETTINGS = {
    "url": "https://example.invalid/louty",
    "username": "user",
    "password": "secret",
    "data_dir": None,
}


def make_folder(parent, name, files=()):
    """Create a folder with empty files; return its path."""
    folder = parent / name
    folder.mkdir()
    for file in files:
        (folder / file).touch()
    return folder


@pytest.fixture
def env(monkeypatch):
    """Isolate main(): fixed settings, no logger setup, recorded Louty calls.

    Returns a dict where the test sets "answer" (what the user types at
    the prompt), "pick" (what the dialog returns) and "louty_ok"; it
    collects "prompts" and "louty_calls".
    """
    state = {
        "answer": "non",
        "pick": None,
        "louty_ok": True,
        "prompts": [],
        "louty_calls": [],
    }

    def fake_input(prompt=""):
        state["prompts"].append(prompt)
        return state["answer"]

    def fake_update_louty(settings, username, password, folder, report, headed):
        state["louty_calls"].append(
            dict(folder=folder, report=report, headed=headed, username=username)
        )
        return state["louty_ok"]

    monkeypatch.setattr(cli, "setup_logger", lambda level: None)
    monkeypatch.setattr(louty, "load_settings", lambda: dict(SETTINGS))
    monkeypatch.setattr(cli, "pick_folder", lambda initial_dir: state["pick"])
    monkeypatch.setattr(cli, "update_louty", fake_update_louty)
    monkeypatch.setattr("builtins.input", fake_input)
    return state


@pytest.fixture
def clean_folder(tmp_path):
    return make_folder(
        tmp_path,
        "2026-10",
        files=["2026-10-01 AWS 33E31.pdf", "2026-01 Pass Navigo 45E40.pdf"],
    )


@pytest.fixture
def faulty_folder(tmp_path):
    return make_folder(
        tmp_path,
        "2026-12",
        files=["2026-12-01 AWS 33E31.pdf", "2026-12-02 Fnac 25E00.pdf"],
    )


# --- arguments ---


def test_parse_args_defaults():
    args = cli.parse_args([])
    assert args.folder is None
    assert not args.headed
    assert not args.debug


def test_parse_args_all():
    args = cli.parse_args([r"C:\Frais\2026-10", "--headed", "--debug"])
    assert args.folder == r"C:\Frais\2026-10"
    assert args.headed
    assert args.debug


# --- folder choice ---


def test_choose_folder_from_argument(monkeypatch):
    monkeypatch.setattr(cli, "pick_folder", lambda initial_dir: pytest.fail())
    assert cli.choose_folder("some/2026-10", None) == Path("some/2026-10")


def test_choose_folder_dialog_opens_in_data_dir(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(cli, "pick_folder", lambda d: seen.append(d) or tmp_path)
    assert cli.choose_folder(None, str(tmp_path)) == tmp_path
    assert seen == [tmp_path]


@pytest.mark.parametrize("data_dir", [None, "Z:/does/not/exist"])
def test_choose_folder_dialog_falls_back_to_home(monkeypatch, data_dir):
    seen = []
    monkeypatch.setattr(cli, "pick_folder", lambda d: seen.append(d))
    assert cli.choose_folder(None, data_dir) is None
    assert seen == [Path.home()]


# --- diagnostics ---


def test_diagnose_clean(clean_folder, capsys):
    report = cli.diagnose(clean_folder)
    assert report["subject"] == "Frais d'Octobre 2026"
    assert len(report["expenses"]) == 2
    out = capsys.readouterr().out
    assert "Objet : Frais d'Octobre 2026" in out
    assert "total 78,71" in out


def test_diagnose_files_to_rename(faulty_folder, capsys):
    assert cli.diagnose(faulty_folder) is None
    out = capsys.readouterr().out
    assert "1 fichier(s) à renommer" in out
    assert "2026-12-02 Fnac 25E00.pdf" in out
    # the accepted expense is still displayed
    assert "AWS" in out


@pytest.mark.parametrize(
    "name, files, message",
    [
        ("Frais", ["2026-10-01 AWS 33E31.pdf"], "YYYY-MM"),
        ("2026-11", [], "No file"),
        ("2026-09", ["scan.png"], "Aucune dépense"),
    ],
)
def test_diagnose_rejected_folders(tmp_path, capsys, name, files, message):
    folder = make_folder(tmp_path, name, files=files)
    assert cli.diagnose(folder) is None
    assert message in capsys.readouterr().out


# --- main ---


def test_main_declined_leaves_louty_untouched(env, clean_folder, capsys):
    env["answer"] = "non"
    assert cli.main([str(clean_folder)]) == 0
    assert len(env["prompts"]) == 1
    assert env["louty_calls"] == []
    assert "Louty n'a pas été modifié" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["", "n", "yes", "ouii"])
def test_main_anything_but_oui_declines(env, clean_folder, answer):
    env["answer"] = answer
    assert cli.main([str(clean_folder)]) == 0
    assert env["louty_calls"] == []


@pytest.mark.parametrize("answer", ["oui", "OUI", " o "])
def test_main_confirmed_updates_louty(env, clean_folder, capsys, answer):
    env["answer"] = answer
    assert cli.main([str(clean_folder), "--headed"]) == 0
    [call] = env["louty_calls"]
    assert call["folder"] == clean_folder.resolve()
    assert call["headed"]
    assert call["username"] == "user"
    assert call["report"]["subject"] == "Frais d'Octobre 2026"
    assert len(call["report"]["expenses"]) == 2
    assert "Note enregistrée en brouillon" in capsys.readouterr().out


def test_main_louty_failure(env, clean_folder, capsys):
    env["answer"] = "oui"
    env["louty_ok"] = False
    assert cli.main([str(clean_folder)]) == 1
    assert "Échec de la mise à jour de Louty" in capsys.readouterr().out


def test_main_folder_with_errors_no_prompt(env, faulty_folder):
    assert cli.main([str(faulty_folder)]) == 1
    assert env["prompts"] == []
    assert env["louty_calls"] == []


def test_main_dialog_cancelled(env, capsys):
    env["pick"] = None
    assert cli.main([]) == 0
    assert env["prompts"] == []
    assert "Aucun dossier choisi" in capsys.readouterr().out


def test_main_dialog_folder(env, clean_folder):
    env["pick"] = clean_folder
    env["answer"] = "oui"
    assert cli.main([]) == 0
    assert len(env["louty_calls"]) == 1


def test_main_asks_missing_credentials(env, clean_folder, monkeypatch):
    monkeypatch.setattr(
        louty, "load_settings", lambda: dict(SETTINGS, username=None, password=None)
    )
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "typed-secret")
    env["answer"] = "oui"
    assert cli.main([str(clean_folder)]) == 0
    # first prompt: confirmation, second: username (answered "oui" here)
    assert len(env["prompts"]) == 2
    assert "username" in env["prompts"][1]
