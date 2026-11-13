"""The perspica path: output for a known JSON document, and shape checks.

The fixture follows perspica's `MultiFileResult` (version, source, files, results,
cross_file). It is hand-written, with field names compared with perspica 0.5.1, so it
guards the script's own rendering. The last test runs the installed perspica, when
there is one, to notice when its real output stops fitting.
"""

import argparse
import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

import change_map

FIXTURES = Path(__file__).parent / "fixtures"


def perspica_data():
    return json.loads((FIXTURES / "perspica.json").read_text(encoding="utf-8"))


def args(**overrides):
    ns = argparse.Namespace(
        perspica_json=None,
        no_perspica=False,
        staged=False,
        uncommitted=False,
        range=None,
        commit=None,
        base=None,
    )
    vars(ns).update(overrides)
    return ns


def test_known_document_renders_as_before(capsys):
    change_map.print_perspica(perspica_data(), "perspica")

    expected = (FIXTURES / "perspica.expected.txt").read_text(encoding="utf-8")
    assert capsys.readouterr().out == expected


def test_valid_document_has_no_problem():
    assert change_map.perspica_problem(perspica_data()) is None


def broken(change):
    data = copy.deepcopy(perspica_data())
    change(data)
    return data


@pytest.mark.parametrize(
    "data, complaint",
    [
        ([], "top level is not an object"),
        ({}, "`files` is missing"),
        (broken(lambda d: d.pop("results")), "`results` is missing"),
        (broken(lambda d: d.pop("cross_file")), "`cross_file` is missing"),
        (broken(lambda d: d.update(files={})), "`files` is not a list"),
        (broken(lambda d: d["results"].pop()), "4 files but 3 results"),
        (broken(lambda d: d["files"][0].pop("new_path")), "files[0] has no `new_path`"),
        (broken(lambda d: d["results"][1].pop("hunks")), "results[1] has no `hunks`"),
        (
            broken(lambda d: d["results"][0].update(manifest=[])),
            "results[0] `manifest` is not an object",
        ),
    ],
)
def test_unexpected_shape_is_reported(data, complaint):
    assert change_map.perspica_problem(data) == complaint


def test_saved_json_with_a_wrong_shape_is_an_error(tmp_path):
    saved = tmp_path / "old.json"
    saved.write_text('{"diffs": []}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="not the perspica JSON this script reads"):
        change_map.load_perspica(args(perspica_json=str(saved)))


def test_live_perspica_with_a_wrong_shape_falls_back_to_git(monkeypatch, capsys):
    monkeypatch.setattr(change_map.shutil, "which", lambda name: "/usr/bin/perspica")
    monkeypatch.setattr(change_map, "run", lambda cmd, check=True: (0, "{}", ""))

    assert change_map.load_perspica(args()) == (None, None)
    assert "`files` is missing" in capsys.readouterr().err


def test_formatting_only_entries_are_listed_as_mechanical(capsys):
    change_map.print_perspica(perspica_data(), "perspica")

    assert (
        "- formatting-only #11 cart.py:30-34: TAX_RATES: formatting/comments only"
        " (mechanical)\n"
    ) in capsys.readouterr().out


def test_perspica_reporting_no_changes_falls_back_quietly(monkeypatch, capsys):
    said = "No changes found (staged changes).\n"
    monkeypatch.setattr(change_map.shutil, "which", lambda name: "/usr/bin/perspica")
    monkeypatch.setattr(change_map, "run", lambda cmd, check=True: (0, "", said))

    assert change_map.load_perspica(args(staged=True)) == (None, None)
    assert capsys.readouterr().err == ""


@pytest.mark.skipif(not shutil.which("perspica"), reason="perspica is not installed")
def test_installed_perspica_still_has_the_shape_this_script_reads(
    tmp_path, monkeypatch, capsys
):
    def git(*cmd):
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *cmd],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q", "-b", "main")
    cart = tmp_path / "cart.py"
    cart.write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    git("add", ".")
    git("commit", "-q", "-m", "one")
    cart.write_text(
        "def total(items, tax=0):\n    return sum(items) * (1 + tax)\n",
        encoding="utf-8",
    )
    git("commit", "-q", "-am", "two")
    monkeypatch.chdir(tmp_path)

    data, analyzer = change_map.load_perspica(args(commit="HEAD"))

    assert analyzer == "perspica", capsys.readouterr().err
    assert change_map.perspica_problem(data) is None
    change_map.print_perspica(data, analyzer)
    out = capsys.readouterr().out
    assert "- cart.py [M · source · Python] changed" in out
    assert "`total`" in out
    assert "return sum(items) * (1 + tax)" in out
    assert "?" not in out.replace("[formatting?]", "")
