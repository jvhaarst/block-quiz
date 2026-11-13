"""--files-only and --path keep a large change out of the context window."""

import json
from pathlib import Path

import pytest

import change_map

FIXTURES = Path(__file__).parent / "fixtures"

RAW = "\n".join(
    [
        "diff --git a/src/cart.py b/src/cart.py",
        "--- a/src/cart.py",
        "+++ b/src/cart.py",
        "@@ -1 +1 @@",
        "-total = 1",
        "+total = 2",
        "diff --git a/lib/util.js b/lib/util.js",
        "--- a/lib/util.js",
        "+++ b/lib/util.js",
        "@@ -1 +1 @@",
        "-let x = 1",
        "+let x = 2",
        "diff --git a/old/name.py b/src/name.py",
        "similarity index 100%",
        "rename from old/name.py",
        "rename to src/name.py",
        "",
    ]
)


def perspica_data():
    return json.loads((FIXTURES / "perspica.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "path, patterns, selected",
    [
        ("src/cart.py", [], True),
        ("src/cart.py", ["src/cart.py"], True),
        ("src/cart.py", ["src"], True),
        ("src/cart.py", ["src/"], True),
        ("src/cart.py", ["*.py"], True),
        ("src/cart.py", ["lib", "src"], True),
        ("src/cart.py", ["lib"], False),
        ("src/cart.py", ["sr"], False),
        ("src/cart.py", ["*.js"], False),
    ],
)
def test_path_selected(path, patterns, selected):
    assert change_map.path_selected(path, patterns) is selected


def test_files_only_lists_files_without_the_diff(capsys):
    change_map.print_git("test", RAW, [], files_only=True)

    out = capsys.readouterr().out
    assert "- src/cart.py [M · source] +1 -1" in out
    assert "- lib/util.js [M · source] +1 -1" in out
    assert "## Diff" not in out
    assert "total = 2" not in out
    assert "--path" in out


def test_path_keeps_only_matching_files(capsys):
    change_map.print_git("test", RAW, [], paths=["lib"])

    out = capsys.readouterr().out
    assert "let x = 2" in out
    assert "total = 2" not in out
    assert "src/cart.py" not in out
    assert "- Showing: 1 of 3 files (--path lib)" in out


def test_path_matches_a_rename_by_its_old_name(capsys):
    change_map.print_git("test", RAW, [], paths=["old"])

    out = capsys.readouterr().out
    assert "- src/name.py (from old/name.py) [R · source]" in out
    assert "- Showing: 1 of 3 files (--path old)" in out


def test_path_applies_to_untracked_files(tmp_path, monkeypatch, capsys):
    (tmp_path / "keep.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "drop.js").write_text("b = 1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    change_map.print_git("test", "", ["keep.py", "drop.js"], paths=["*.py"])

    out = capsys.readouterr().out
    assert "a = 1" in out
    assert "drop.js" not in out


def test_path_that_matches_nothing_is_an_error():
    with pytest.raises(RuntimeError, match="no changed file matches --path nope"):
        change_map.print_git("test", RAW, [], paths=["nope"])


def test_unfiltered_output_has_no_showing_line(capsys):
    change_map.print_git("test", RAW, [])

    assert "Showing:" not in capsys.readouterr().out


def test_perspica_files_only_stops_after_the_structure(capsys):
    change_map.print_perspica(perspica_data(), "perspica", files_only=True)

    out = capsys.readouterr().out
    assert "## Files" in out
    assert "## Reading order" in out
    assert "## Classified changes" in out
    assert "## Diff" not in out


def test_perspica_path_keeps_only_matching_files(capsys):
    change_map.print_perspica(perspica_data(), "perspica", paths=["b.py"])

    out = capsys.readouterr().out
    assert "- a.py -> b.py [" in out
    assert "- cart.py [" not in out
    assert "### cart.py" not in out
    assert "- logic #1" not in out
    assert "- Showing: 1 of 4 files (--path b.py)" in out
