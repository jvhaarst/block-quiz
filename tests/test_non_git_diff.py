"""Plain `diff -u` output has no `diff --git` line, only ---/+++ headers."""

import pytest

import change_map

PLAIN = "\n".join(
    [
        "--- old/cart.py\t2026-11-01 10:00:00.000000000 +0100",
        "+++ new/cart.py\t2026-11-02 10:00:00.000000000 +0100",
        "@@ -1,2 +1,2 @@",
        " def total():",
        "-    return 1",
        "+    return 2",
        "--- old/util.py\t2026-11-01 10:00:00.000000000 +0100",
        "+++ new/util.py\t2026-11-02 10:00:00.000000000 +0100",
        "@@ -5 +5 @@",
        "-x = 1",
        "+x = 2",
        "",
    ]
)


def test_plain_unified_diff_is_parsed_per_file():
    files = change_map.parse_unified(PLAIN)

    assert [(f["old"], f["new"]) for f in files] == [
        ("old/cart.py", "new/cart.py"),
        ("old/util.py", "new/util.py"),
    ]
    assert files[0]["hunks"][0]["lines"] == [
        (" ", 1, "def total():"),
        ("-", 2, "    return 1"),
        ("+", 2, "    return 2"),
    ]
    assert files[1]["hunks"][0]["lines"] == [("-", 5, "x = 1"), ("+", 5, "x = 2")]


def test_plain_diff_against_dev_null_is_an_added_or_deleted_file():
    raw = "\n".join(
        [
            "--- /dev/null",
            "+++ b/new.py",
            "@@ -0,0 +1 @@",
            "+x = 1",
            "--- a/gone.py",
            "+++ /dev/null",
            "@@ -1 +0,0 @@",
            "-y = 1",
            "",
        ]
    )

    files = change_map.parse_unified(raw)

    assert [(f["status"], f["old"], f["new"]) for f in files] == [
        ("A", "new.py", "new.py"),
        ("D", "gone.py", "gone.py"),
    ]


def test_git_diff_headers_do_not_create_a_second_file():
    raw = "\n".join(
        [
            "diff --git a/f.py b/f.py",
            "index 1111111..2222222 100644",
            "--- a/f.py",
            "+++ b/f.py",
            "@@ -1 +1 @@",
            "-a = 1",
            "+a = 2",
            "",
        ]
    )

    files = change_map.parse_unified(raw)

    assert [(f["old"], f["new"]) for f in files] == [("f.py", "f.py")]


def test_input_without_any_diff_is_an_error_not_an_empty_map():
    with pytest.raises(RuntimeError, match="no diff found"):
        change_map.print_git("patch file notes.txt", "just some notes\nnot a diff\n", [])
