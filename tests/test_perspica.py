"""The perspica path: output for a known JSON document, and shape checks.

The fixture follows perspica's `MultiFileResult` (version, source, files, results,
cross_file). It is hand-written from the field names the script reads, so it guards
the script's own rendering, not perspica's real output.
"""

import argparse
import copy
import json
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
